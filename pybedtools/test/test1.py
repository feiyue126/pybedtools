import pybedtools
import os, difflib, sys
from nose import with_setup
from nose.tools import assert_raises, raises
from pybedtools.helpers import BEDToolsError
from pybedtools import featurefuncs
from tfuncs import setup, teardown, testdir, test_tempdir, unwriteable


def fix(x):
    """
    Replaces spaces with tabs, removes spurious newlines, and lstrip()s each
    line. Makes it really easy to create BED files on the fly for testing and
    checking.
    """
    s = ""
    for i in  x.splitlines():
        i = i.lstrip()
        if i.endswith('\t'):
            add_tab = '\t'
        else:
            add_tab = ''
        if len(i) == 0:
            continue
        i = i.split()
        i = '\t'.join(i) + add_tab + '\n'
        s += i
    return s


# ----------------------------------------------------------------------------
# Tabix support tests
# ----------------------------------------------------------------------------

def make_unwriteable():
    """
    Make a directory that cannot be written to and set the pybedtools tempdir
    to it. This is used to isolate "streaming" tests to ensure they do not
    write to disk.
    """
    if os.path.exists(unwriteable):
        os.system('rm -rf %s' % unwriteable)
    os.system('mkdir -p %s' % unwriteable)
    os.system('chmod -w %s' % unwriteable)
    pybedtools.set_tempdir(unwriteable)

def cleanup_unwriteable():
    """
    Reset to normal tempdir operation....
    """
    if os.path.exists(unwriteable):
        os.system('rm -rf %s' % unwriteable)
    pybedtools.set_tempdir(test_tempdir)

def test_interval_index():
    """
    supplement to the more general test in test_cbedtools.IntervalTest.testGetItemNegative
    """
    iv = pybedtools.create_interval_from_list('chr21   9719768 9721892 ALR/Alpha       1004    +'.split())
    assert iv[-1] == '+'
    assert iv[2:-1] == ['9721892', 'ALR/Alpha', '1004']

    iv = pybedtools.create_interval_from_list(
            ['chr1', 'ucb', 'gene', '465', '805', '.', '+', '.',
                'ID=thaliana_1_465_805;match=scaffold_801404.1;rname=thaliana_1_465_805'])
    print iv[4:-3]
    assert iv[4:-3] == ['805', '.']

def test_tuple_creation():
    # everything as a string
    t = [
            ("chr1", "1", "100", "feature1", "0", "+"),
            ("chr1", "100", "200", "feature2", "0", "+"),
            ("chr1", "150", "500", "feature3", "0", "-"),
            ("chr1", "900", "950", "feature4", "0", "+")
        ]
    x = pybedtools.BedTool(t).saveas()
    assert pybedtools.example_bedtool('a.bed') == x

    t = [
            ("chr1", 1, 100, "feature1", 0, "+"),
            ("chr1", 100, 200, "feature2", 0, "+"),
            ("chr1", 150, 500, "feature3", 0, "-"),
            ("chr1", 900, 950, "feature4", 0, "+")
        ]
    x = pybedtools.BedTool(t).saveas()
    assert pybedtools.example_bedtool('a.bed') == x

    t = [
            ("chr1", "fake", "gene", "50", "300", ".", "+", ".", "ID=gene1"),
            ("chr1", "fake", "mRNA", "50", "300", ".", "+", ".", "ID=mRNA1;Parent=gene1;"),
            ("chr1", "fake", "CDS", "75", "150", ".", "+", ".", "ID=CDS1;Parent=mRNA1;"),
            ("chr1", "fake", "CDS", "200", "275", ".", "+", ".", "ID=CDS2;Parent=mRNA1;"),
            ("chr1", "fake", "rRNA", "1200", "1275", ".", "+", ".", "ID=rRNA1;"),]
    x = pybedtools.BedTool(t).saveas()

    # Make sure that x has actual Intervals and not plain tuples or something
    assert isinstance(x[0], pybedtools.Interval)
    assert repr(x[0]) == "Interval(chr1:49-300)"
    assert x[0]['ID'] == 'gene1'


def test_tabix():
    a = pybedtools.example_bedtool('a.bed')
    t = a.tabix()
    assert t._tabixed()
    results = str(t.tabix_intervals('chr1:99-200'))
    print results
    assert results == fix("""
    chr1	1	100	feature1	0	+
    chr1	100	200	feature2	0	+
    chr1	150	500	feature3	0	-""")

    assert str(t.tabix_intervals(a[2])) == fix("""
    chr1	100	200	feature2	0	+
    chr1	150	500	feature3	0	-""")

    # clean up
    fns = [
            pybedtools.example_filename('a.bed.gz'),
            pybedtools.example_filename('a.bed.gz.tbi'),
          ]
    for fn in fns:
        if os.path.exists(fn):
            os.unlink(fn)

def test_tabix_intervals():
    a = pybedtools.BedTool('chr1 25 30', from_string=True).tabix()
    assert len(a.tabix_intervals('chr1:30-35')) == 0
    assert len(a.tabix_intervals('chr1:29-30')) == 1

    # make sure it works OK even if strand was provided
    assert len(a.tabix_intervals('chr1:30-35[-]')) == 0
    assert len(a.tabix_intervals('chr1:29-30[-]')) == 1

# ----------------------------------------------------------------------------
# Streaming and non-file BedTool tests
# ----------------------------------------------------------------------------

@with_setup(make_unwriteable, cleanup_unwriteable)
def test_stream():
    """
    Stream and file-based equality, both whole-file and Interval by
    Interval
    """
    cleanup_unwriteable()

    a = pybedtools.example_bedtool('a.bed')
    b = pybedtools.example_bedtool('b.bed')
    c = a.intersect(b)

    # this should really not be written anywhere
    d = a.intersect(b, stream=True)

    assert_raises(NotImplementedError, c.__eq__, d)
    d_contents = d.fn.read()
    c_contents = open(c.fn).read()
    assert d_contents == c_contents

    # reconstruct d and check Interval-by-Interval equality
    make_unwriteable()
    d = a.intersect(b, stream=True)

    for i,j in zip(c, d):
        assert str(i) == str(j)

    # Now do something similar with GFF files.
    a = pybedtools.example_bedtool('a.bed')
    f = pybedtools.example_bedtool('d.gff')

    # file-based
    cleanup_unwriteable()
    g1 = f.intersect(a)

    # streaming
    make_unwriteable()
    g2 = f.intersect(a, stream=True)

    for i,j in zip(g1, g2):
        assert str(i) == str(j)

    # this was segfaulting at one point, just run to make sure
    g3 = f.intersect(a, stream=True)
    for i in iter(g3):
        print i

    for row in a.cut([0, 1, 2, 5], stream=True):
        row[0], row[1], row[2]
        assert_raises(IndexError, row.__getitem__, 4)

def test_stream_of_stream():
    """
    Second-level streaming using self-intersections
    """
    a = pybedtools.example_bedtool('a.bed')

    # Ensure non-stream and stream equality of self-intersection
    nonstream1 = a.intersect(a, u=True)
    stream1    = a.intersect(a, u=True, stream=True)
    nonstream1_str = str(nonstream1)
    stream1_str    = str(stream1)
    a_str          = str(a)
    assert nonstream1_str == stream1_str == a_str

    # Have to reconstruct stream1 cause it was consumed in the str() call
    nonstream1 = a.intersect(a, u=True)
    stream1    = a.intersect(a, u=True, stream=True)
    nonstream2 = a.intersect(nonstream1, u=True)
    stream2    = a.intersect(stream1, u=True, stream=True)
    nonstream2_str = str(nonstream2)
    stream2_str    = str(stream2)
    assert nonstream2_str == stream2_str == nonstream1_str == stream1_str == a_str

def test_generator():
    """
    Equality of BedTools created from file, iter(), and generator
    """
    # Test creation from file vs
    a = pybedtools.example_bedtool('a.bed')
    b = pybedtools.BedTool(iter(a))
    assert str(a) == str(b)

    # Ensure that streams work well too
    b1 = a.intersect(a, stream=True)
    b2 = pybedtools.BedTool((i for i in a)).intersect(a)
    assert str(b1) == str(b2)

def test_stream_of_generator():
    a = pybedtools.example_bedtool('a.bed')
    b = pybedtools.example_bedtool('b.bed')
    b1 = a.intersect(a, stream=True)
    b2 = pybedtools.BedTool((i for i in a)).intersect(a, stream=True)
    sb1 = str(b1)
    sb2 = str(b2)
    print sb1
    print sb2
    assert sb1 == sb2

def test_many_files():
    """regression test to make sure many files can be created
    """
    a = pybedtools.example_bedtool('a.bed')
    b = pybedtools.example_bedtool('b.bed')
    # Previously, IntervalFile would leak open files and would cause OSError
    # (too many open files) at iteration 1010 or so.
    for i in xrange(1100):
        c = a.intersect(b)

def test_malformed():
    """
    Malformed BED lines should raise MalformedBedLineError
    """
    a = pybedtools.BedTool("""
    chr1 100 200
    chr1 100 90
    chr1 100 200
    chr1 100 200
    chr1 100 200
    chr1 100 200
    """, from_string=True)
    a_i = iter(a)

    # first feature is OK
    print a_i.next()

    # but next one is not and should raise exception
    assert_raises(pybedtools.MalformedBedLineError, a_i.next)

def test_remove_invalid():
    """
    Remove_invalid() removes invalid lines, track lines, and comments
    """
    a = pybedtools.BedTool("""
    chr1 100 200
    chr1 100 90
    track name='try to break parser'
    chr1 100 200
    chr1 100 200
    chr1 100 200
    #
    chr1 100 200
    """, from_string=True)

    b = a.remove_invalid()

    cleaned = pybedtools.BedTool("""
    chr1 100 200
    chr1 100 200
    chr1 100 200
    chr1 100 200
    chr1 100 200""", from_string=True)

    assert_raises(NotImplementedError, b.__eq__, cleaned)
    assert str(b) == str(cleaned)

def test_create_from_list_long_features():
    """
    Iterator handles extra fields from long features (BED+GFF -wao intersection)
    """
    a = pybedtools.example_bedtool('a.bed')
    b = pybedtools.example_bedtool('c.gff')
    c = a.intersect(b, wao=True, stream=False)
    d = a.intersect(b, wao=True, stream=True)

    print b.closest(a)

    for i in d:
        print i

def test_iterator():
    """
    Iterator should ignore non-BED lines
    """
    s = """
    track name="test"


    browser position chrX:1-100
    # comment line
    chrX  1 10
    # more comments
    track name="another"


    """
    a = pybedtools.BedTool(s, from_string=True)
    results = list(a)
    print results[0]
    assert str(results[0]) == 'chrX\t1\t10\n', results

def test_indexing():
    """
    Indexing into BedTools
    """
    a = pybedtools.example_bedtool('a.bed')

    # This is the first line
    interval = pybedtools.Interval('chr1', 1, 100, 'feature1', '0', '+')

    # just to make sure
    assert interval == iter(a).next()

    # test slice behavior
    results = list(a[0:2])
    assert len(results) == 2
    assert results[0] == interval

    # test single-integer indexing
    assert a[0] == interval

    # only slices and integers allowed....
    assert_raises(ValueError, a.__getitem__, 'key')

def test_repr_and_printing():
    """
    Missing files and streams should say so in repr()
    """
    a = pybedtools.example_bedtool('a.bed')
    b = pybedtools.example_bedtool('b.bed')
    c = a+b
    d = a.intersect(b, stream=True)
    os.unlink(c.fn)
    assert 'a.bed' in repr(a)
    assert 'b.bed' in repr(b)
    assert 'MISSING FILE' in repr(c)
    assert 'stream' in repr(d)

def test_file_type():
    """
    Regression test on file_type checks

    Previously file_type was creating a new IntervalFile every time it was
    called; now it's cached so an IntervalFile is only created once per
    BedTool.
    """
    a = pybedtools.example_bedtool('a.bed')
    for i in range(5000):
        a.file_type

# ----------------------------------------------------------------------------
# BEDTools wrapper tests --
#   See test_iter.py, which uses YAML test case definitions, for more complete
#   tests of BEDTools wrapper methods.
#
#   Here, we assert exception raises and more complicated things that can't be
#   easily described in YAML
# ----------------------------------------------------------------------------

def test_introns():
    a = pybedtools.example_bedtool('mm9.bed12')
    b = pybedtools.BedTool((f for f in a if f.name == "Tcea1,uc007afj.1")).saveas()
    bfeat = iter(b).next()

    bi = b.introns()
    # b[9] is the exonCount from teh bed12 file. there should be
    # b[9] -1 introns assuming no utrs.
    assert len(bi) == int(bfeat[9]) - 1, (len(bi), len(b))

def test_slop():
    """
    Calling slop with no genome should raise ValueError
    """
    a = pybedtools.example_bedtool('a.bed')

    # Make sure it complains if no genome is set
    assert_raises(ValueError, a.slop, **dict(l=100, r=1))

def test_closest():
    a = pybedtools.example_bedtool('a.bed')
    b = pybedtools.example_bedtool('b.bed')
    r = a.closest(b)
    assert len(r) == len(a)

# TODO: there's enough stuff in here that it's probably worth it to eventually
# make a TestSequenceStuff class
def test_sequence():
    """
    From UCSC:

    chromStart - The starting position of the feature in the chromosome or
    scaffold. The first base in a chromosome is numbered 0.

    chromEnd - The ending position of the feature in the chromosome or
    scaffold. The chromEnd base is not included in the display of the feature.
    For example, the first 100 bases of a chromosome are defined as
    chromStart=0, chromEnd=100, and span the bases numbered 0-99. """

    fi = os.path.join(testdir, 'test.fasta')

    s = """
    chrX 9  16 . . +
    chrX 9  16 . . -
    chrY 1  4  . . +
    chrZ 28 31 . . +
    """

    fasta = """
    >chrX
    AAAAAAAAATGCACTGAAAAAAAAAAAAAAA
    >chrY
    GCTACCCCCCCCCCCCCCCCCCCCCCCCCCC
    >chrZ
    AAAAAAAAAAAAAAAAAAAAAAAAAAAATCT
    """
    a = pybedtools.BedTool(s, from_string=True)
    assert_raises(ValueError, a.save_seqs, ('none',))

    fout = open(fi,'w')
    for line in fasta.splitlines(True):
        fout.write(line.lstrip())
    fout.close()

    # redirect stderr for the call to .sequence(), which reports the creation
    # of an index file
    tmp = open(a._tmp(),'w')
    orig_stderr = sys.stderr
    sys.stderr = tmp

    f = a.sequence(fi=fi)

    sys.stderr = orig_stderr

    assert f.fn == f.fn
    seqs = open(f.seqfn).read()
    print seqs
    expected = """>chrX:9-16
TGCACTG
>chrX:9-16
TGCACTG
>chrY:1-4
CTA
>chrZ:28-31
TCT
"""
    print ''.join(difflib.ndiff(seqs,expected))
    print expected
    assert seqs == expected

    f = a.sequence(fi=fi,s=True)
    seqs = open(f.seqfn).read()
    expected = """>chrX:9-16(+)
TGCACTG
>chrX:9-16(-)
CAGTGCA
>chrY:1-4(+)
CTA
>chrZ:28-31(+)
TCT
"""
    print seqs
    print expected
    print ''.join(difflib.ndiff(seqs,expected))
    assert seqs == expected

    f = f.save_seqs('deleteme.fa')
    assert open('deleteme.fa').read() == expected
    assert f.print_sequence() == expected
    os.unlink('deleteme.fa')

    fresh_a = pybedtools.BedTool(s, from_string=True)
    assert fresh_a == f

    os.unlink(fi)
    if os.path.exists(fi+'.fai'):
        os.unlink(fi+'.fai')

# ----------------------------------------------------------------------------
# Operator tests
# ----------------------------------------------------------------------------
def test_add_subtract():
    a = pybedtools.example_bedtool('a.bed')
    b = pybedtools.example_bedtool('b.bed')
    assert a.intersect(b,u=True) == (a+b)
    assert a.intersect(b,v=True) == (a-b)

def test_subset():
    a = pybedtools.example_bedtool('a.bed')
    import random
    random.seed(1)

    s = list(a.random_subset(1).features())
    assert len(s) == 1
    assert isinstance(s[0], pybedtools.Interval)

    s2 = list(a.random_subset(len(a)).features())
    print len(s2)
    assert len(s2) == len(a)

def test_eq():
    a = pybedtools.example_bedtool('a.bed')
    b = pybedtools.example_bedtool('a.bed')

    # BedTool to BedTool
    assert a == b

    # BedTool to string
    s= """chr1	1	100	feature1	0	+
chr1	100	200	feature2	0	+
chr1	150	500	feature3	0	-
chr1	900	950	feature4	0	+
"""
    assert a == s
    # Test not equa on bedtool
    b = pybedtools.example_bedtool('b.bed')
    assert b != a

    # and string
    assert a != "blah"

    # Don't allow testing equality on streams
    c = a.intersect(b, stream=True)
    d = a.intersect(b)
    assert_raises(NotImplementedError, c.__eq__, d)
    assert_raises(NotImplementedError, d.__eq__, c)

    # Test it on iterator, too....
    e = pybedtools.BedTool((i for i in a))
    assert_raises(NotImplementedError, e.__eq__, a)
    assert_raises(NotImplementedError, a.__eq__, e)

    # Make sure that if we force the iterator to be consumed, it is in fact
    # equal
    s = str(e)
    print str(a).splitlines(True)
    print s.splitlines(True)
    assert a == s

def test_hash():
    a = pybedtools.example_bedtool('a.bed')
    d = {}
    for i in a:
        d[i] = 1


# ----------------------------------------------------------------------------
# Other BedTool method tests
# ----------------------------------------------------------------------------

def test_count_bed():
    a = pybedtools.example_bedtool('a.bed')
    assert a.count() == 4
    assert len(a) == 4

def test_feature_centers():
    from pybedtools import featurefuncs
    a = pybedtools.BedTool("""
                           chr1 1 100
                           chr5 3000 4000
                           """, from_string=True)
    b = a.each(featurefuncs.center, 1)
    results = list(b.features())

    print results

    assert results[0].start == 50
    assert results[0].stop == 51
    assert results[0].chrom == 'chr1'

    assert results[1].start == 3500
    assert results[1].stop == 3501
    assert results[1].chrom == 'chr5'

def test_bedtool_creation():
    # make sure we can make a bedtool from a bedtool and that it points to the
    # same file
    a = pybedtools.example_bedtool('a.bed')
    b = pybedtools.BedTool(a)
    assert b.fn == a.fn
    assert_raises(ValueError, pybedtools.BedTool,'nonexistent.bed')

    # note that *s* has both tabs and spaces....
    s = """
    chr1	1	100	feature1  0	+
    chr1	100	200	feature2  0	+
    chr1	150	500	feature3  0	-
    chr1	900	950	feature4  0	+
    """
    from_string = pybedtools.BedTool(s, from_string=True)

    # difflib used here to show a bug where a newline was included when using
    # from_string
    print ''.join(difflib.ndiff(str(from_string), str(a)))

    assert str(from_string) == str(a)

def test_special_methods():
    # note that *s* has both tabs and spaces....
    s = """
    chr1	1	100	feature1  0	+
    chr1	100	200	feature2  0	+
    chr1	150	500	feature3  0	-
    chr1	900	950	feature4  0	+
    """
    from_string = pybedtools.BedTool(s, from_string=True)
    a = pybedtools.example_bedtool('a.bed')
    b = pybedtools.example_bedtool('b.bed')

    assert from_string == a
    assert from_string != b
    assert not from_string == b
    assert not from_string != a

def test_field_count():
    a = pybedtools.example_bedtool('a.bed')
    assert a.field_count() == 6

def test_repr_and_printing():
    a = pybedtools.example_bedtool('a.bed')
    b = pybedtools.example_bedtool('b.bed')
    c = a+b
    os.unlink(c.fn)
    assert 'a.bed' in repr(a)
    assert 'b.bed' in repr(b)
    assert 'MISSING FILE' in repr(c)

    print a.head(1)

def test_cut():
    a = pybedtools.example_bedtool('a.bed')
    c = a.cut([0, 1, 2, 4])
    assert c.field_count() == 4, c

def test_filter():
    a = pybedtools.example_bedtool('a.bed')

    b = a.filter(lambda f: f.length < 100 and f.length > 0)
    assert len(b) == 2

def test_random_intersection():
    # TODO:
    return
    N = 4
    a = pybedtools.example_bedtool('a.bed')
    b = pybedtools.example_bedtool('b.bed')
    li = list(a.randomintersection(b, N))
    assert len(li) == N, li

def test_cat():
    a = pybedtools.example_bedtool('a.bed')
    b = pybedtools.example_bedtool('b.bed')
    b_fn = pybedtools.example_filename('b.bed')
    assert a.cat(b) == a.cat(b_fn)
    expected =  fix("""
    chr1 1   500
    chr1 800 950
    """)
    assert a.cat(b) == expected

    a = pybedtools.example_bedtool('a.bed')
    b = pybedtools.example_bedtool('b.bed')
    c = a.cat(b, postmerge=False)
    assert len(a) + len(b) == len(c), (len(a), len(b), len(c))

    print c
    assert c == fix("""
    chr1	1	100	feature1	0	+
    chr1	100	200	feature2	0	+
    chr1	150	500	feature3	0	-
    chr1	900	950	feature4	0	+
    chr1	155	200	feature5	0	-
    chr1	800	901	feature6	0	+
    """)

def test_randomstats():
    chromsizes = {'chr1':(1,1000)}
    a = pybedtools.example_bedtool('a.bed').set_chromsizes(chromsizes)
    b = pybedtools.example_bedtool('b.bed')
    try:
        results = a.randomstats(b, 100, debug=True)
        assert results['actual'] == 3
        assert results['median randomized'] == 2.0
        assert results['percentile'] == 89.5

    except ImportError:
        # allow doctests to pass if SciPy not installed
        sys.stderr.write('SciPy not installed, so not testing '
                         'BedTool.randomstats().')


# ----------------------------------------------------------------------------
# Interval tests
# ----------------------------------------------------------------------------

def test_gff_stuff():
    s = """
    chr1  fake  gene 1 100 . + . ID=gene1
    chr1  fake  mRNA 1 100 . + . Name=mRNA1
    chr1  fake  CDS 50 90 . + . other=nothing
    """
    d = pybedtools.BedTool(s, from_string=True)
    f1, f2, f3 = d.features()
    assert f1.name == 'gene1', f1.name
    assert f2.name == 'mRNA1', f2.name
    assert f3.name is None, f3.name

def test_name():
    c = iter(pybedtools.example_bedtool('c.gff')).next()
    assert c.name == "thaliana_1_465_805" , c.name

# ----------------------------------------------------------------------------
# Other non-BedTool tests
# ----------------------------------------------------------------------------

def test_flatten():
    from pybedtools.helpers import _flatten_list
    result = _flatten_list([[1,2,3,0,[0,5],9],[100]])
    print result
    assert result == [1, 2, 3, 0, 0, 5, 9, 100]

def test_history_step():
    a = pybedtools.example_bedtool('a.bed')
    b = pybedtools.example_bedtool('b.bed')
    c = a.intersect(b)
    d = c.subtract(a)

    tag = c.history[0].result_tag
    assert pybedtools.find_tagged(tag) == c

    assert_raises(ValueError, pybedtools.find_tagged, 'nonexistent')


    print d.history
    d.delete_temporary_history(ask=True, raw_input_func=lambda x: 'n')
    assert os.path.exists(a.fn)
    assert os.path.exists(b.fn)
    assert os.path.exists(c.fn)
    assert os.path.exists(d.fn)

    d.delete_temporary_history(ask=True, raw_input_func=lambda x: 'Yes')
    assert os.path.exists(a.fn)
    assert os.path.exists(b.fn)
    assert not os.path.exists(c.fn) # this is the only thing that should change
    assert os.path.exists(d.fn)

    a = pybedtools.example_bedtool('a.bed')
    b = pybedtools.example_bedtool('b.bed')
    c = a.intersect(b)
    d = c.subtract(a)
    d.delete_temporary_history(ask=False)
    assert os.path.exists(a.fn)
    assert os.path.exists(b.fn)
    assert not os.path.exists(c.fn) # this is the only thing that should change
    assert os.path.exists(d.fn)

def test_kwargs():
    a = pybedtools.example_bedtool('a.bed')
    b = a.intersect(a, s=False)
    c = a.intersect(a)
    assert str(b) == str(c)


# ----------------------------------------------------------------------------
# gzip support tests
# ----------------------------------------------------------------------------

def test_gzip():
    # make new gzipped files on the fly
    agz = pybedtools.BedTool._tmp()
    bgz = pybedtools.BedTool._tmp()
    os.system('gzip -c %s > %s' % (pybedtools.example_filename('a.bed'), agz))
    os.system('gzip -c %s > %s' % (pybedtools.example_filename('b.bed'), bgz))
    agz = pybedtools.BedTool(agz)
    bgz = pybedtools.BedTool(bgz)
    assert agz.file_type == bgz.file_type == 'bed'
    a = pybedtools.example_bedtool('a.bed')
    b = pybedtools.example_bedtool('b.bed')
    assert a.intersect(b) == agz.intersect(bgz) == a.intersect(bgz) == agz.intersect(b)

# ----------------------------------------------------------------------------
# BAM support tests
# ----------------------------------------------------------------------------
def test_bam_bedtool_creation():
    x = pybedtools.example_bedtool('x.bam')
    a = pybedtools.example_bedtool('a.bed')
    assert x._isbam
    assert not a._isbam

def test_print_abam():
    x = pybedtools.example_bedtool('gdc.bam')
    expected = fix("""
    None	0	chr2L	11	255	5M	*	0	0	CGACA	IIIII	NM:i:0	NH:i:1
    None	16	chr2L	71	255	5M	*	0	0	TTCTC	IIIII	NM:i:0	NH:i:1
    None	16	chr2L	141	255	5M	*	0	0	CACCA	IIIII	NM:i:0	NH:i:1
    None	16	chr2L	151	255	5M	*	0	0	GTTCA	IIIII	NM:i:0	NH:i:1
    None	0	chr2L	211	255	5M	*	0	0	AAATA	IIIII	NM:i:0	NH:i:1
    None	0	chr2L	71	255	5M	*	0	0	GAGAA	IIIII	NM:i:0	NH:i:1
    None	0	chr2L	141	255	5M	*	0	0	TGGTG	IIIII	NM:i:0	NH:i:1
    None	0	chr2L	161	255	5M	*	0	0	GATAA	IIIII	NM:i:0	NH:i:1""")
    print 'x:'
    print x
    print 'expected:'
    print expected
    assert x == expected

def test_bam_iter():
    x = pybedtools.example_bedtool('gdc.bam')
    s = 'None	0	chr2L	11	255	5M	*	0	0	CGACA	IIIII	NM:i:0	NH:i:1\n'
    assert str(x[0]) == str(iter(x).next()) == s

def test_bam_stream_bed():
    x = pybedtools.example_bedtool('gdc.bam')
    b = pybedtools.example_bedtool('gdc.gff')
    c = x.intersect(b, u=True, bed=True, stream=True)
    str_c = str(c)
    expected = fix("""
    chr2L	70	75	None	255	-	70	75	0,0,0	1	5,	0,
    chr2L	140	145	None	255	-	140	145	0,0,0	1	5,	0,
    chr2L	150	155	None	255	-	150	155	0,0,0	1	5,	0,
    chr2L	210	215	None	255	+	210	215	0,0,0	1	5,	0,
    chr2L	70	75	None	255	+	70	75	0,0,0	1	5,	0,
    chr2L	140	145	None	255	+	140	145	0,0,0	1	5,	0,
    chr2L	160	165	None	255	+	160	165	0,0,0	1	5,	0,
    """)
    assert str_c == expected

def test_bam_stream_bam():
    x = pybedtools.example_bedtool('gdc.bam')
    b = pybedtools.example_bedtool('gdc.gff')
    c = x.intersect(b, u=True, stream=True)
    expected = fix("""
    None	16	chr2L	71	255	5M	*	0	0	TTCTC	IIIII	NM:i:0	NH:i:1
    None	16	chr2L	141	255	5M	*	0	0	CACCA	IIIII	NM:i:0	NH:i:1
    None	16	chr2L	151	255	5M	*	0	0	GTTCA	IIIII	NM:i:0	NH:i:1
    None	0	chr2L	211	255	5M	*	0	0	AAATA	IIIII	NM:i:0	NH:i:1
    None	0	chr2L	71	255	5M	*	0	0	GAGAA	IIIII	NM:i:0	NH:i:1
    None	0	chr2L	141	255	5M	*	0	0	TGGTG	IIIII	NM:i:0	NH:i:1
    None	0	chr2L	161	255	5M	*	0	0	GATAA	IIIII	NM:i:0	NH:i:1""")
    assert str(c) == expected

def test_bam_stream_bam_stream():
    x = pybedtools.example_bedtool('gdc.bam')
    b = pybedtools.example_bedtool('gdc.gff')
    c = x.intersect(b, u=True, stream=True)
    expected = fix("""
    None	16	chr2L	71	255	5M	*	0	0	TTCTC	IIIII	NM:i:0	NH:i:1
    None	16	chr2L	141	255	5M	*	0	0	CACCA	IIIII	NM:i:0	NH:i:1
    None	16	chr2L	151	255	5M	*	0	0	GTTCA	IIIII	NM:i:0	NH:i:1
    None	0	chr2L	211	255	5M	*	0	0	AAATA	IIIII	NM:i:0	NH:i:1
    None	0	chr2L	71	255	5M	*	0	0	GAGAA	IIIII	NM:i:0	NH:i:1
    None	0	chr2L	141	255	5M	*	0	0	TGGTG	IIIII	NM:i:0	NH:i:1
    None	0	chr2L	161	255	5M	*	0	0	GATAA	IIIII	NM:i:0	NH:i:1""")
    d = c.intersect(b)
    print d
    assert str(d) == expected

def test_bam_interval():
    x = pybedtools.example_bedtool('x.bam')
    assert x[0].chrom == 'chr2L'
    assert x[0].start == 9329L
    assert x[0][3] == '9330'
    assert x[0].stop == 9365L
    assert len(x[0][9]) == len(x[0]) == 36

def test_bam_regression():
    # Regression test:  with extra fields, the first item in x.bam was being
    # parsed as gff (cause not ==13 fields).  This does a check to prevent that
    # from happening again.
    x = pybedtools.example_bedtool('x.bam')
    assert x[0].file_type == 'sam'
    assert x[0].chrom == 'chr2L'

def test_sam_filetype():
    # file_type was segfaulting cause IntervalFile couldn't parse SAM
    a = pybedtools.example_bedtool('gdc.bam')
    b = pybedtools.BedTool(i for i in a).saveas()
    assert b.file_type == 'sam'

def test_bam_to_sam_to_bam():
    a = pybedtools.example_bedtool('gdc.bam')
    orig = str(a)
    assert a.file_type == 'bam'

    # saveas should maintain BAM format
    b = a.saveas()
    assert b.file_type == 'bam'

    # Converting to string gets SAM format
    assert str(b) == orig

    # b is a bam; to_bam should return a bam
    c = b.to_bam(genome='dm3')
    assert c.file_type == 'bam'

    # in fact, it should be the same file:
    assert c.fn == b.fn

    # In order to get SAM format, need to print to file.
    d = open(pybedtools.BedTool._tmp(), 'w')
    d.write(str(c))
    d.close()
    d = pybedtools.BedTool(d.name)
    assert d.file_type == 'sam'

    e = d.to_bam(genome='dm3')
    assert e.file_type == 'bam'

    # everybody should be the same
    assert a == b == c == d == e


def test_bam_filetype():
    # regression test -- this was segfaulting before because IntervalFile
    # couldn't parse SAM
    a = pybedtools.example_bedtool('gdc.bam')
    b = pybedtools.example_bedtool('gdc.gff')
    c = a.intersect(b)
    assert c.file_type == 'bam'

def test_bam_header():
    a = pybedtools.example_bedtool('gdc.bam')
    b = pybedtools.example_bedtool('gdc.gff')
    c = a.intersect(b)
    print c._bam_header
    assert c._bam_header == "@SQ	SN:chr2L	LN:23011544\n"

def test_output_kwarg():
    a = pybedtools.example_bedtool('a.bed')
    b = pybedtools.example_bedtool('b.bed')
    c = a.intersect(b)
    d = a.intersect(b, output='deleteme.bed')
    assert c == d
    os.unlink('deleteme.bed')

def test_copy():
    a = pybedtools.example_bedtool('a.bed')
    x = a[0]

    # Before adding the __copy__ method to Interval class, making a copy would
    # hang and then segfault
    import copy
    y = copy.copy(x)

    assert y.start == x.start
    assert y.stop == x.stop
    assert y.chrom == x.chrom
    assert y.name == x.name
    assert y.fields == x.fields
    assert y.file_type == x.file_type == 'bed'

    # Make sure it's a real copy (changing something in y doesn't change
    # something in x)
    y.start += 1
    assert y.start == x.start + 1

def test_pickleable():
    interval = pybedtools.create_interval_from_list(
        ['chr1', '1', '100', 'asdf'])
    fn = pybedtools.BedTool._tmp()
    import pickle
    out = open(fn, 'w')
    pickle.dump(interval, out)
    out.close()
    new_interval = pickle.load(open(fn))
    assert str(interval) == str(new_interval)

    interval = pybedtools.create_interval_from_list(
        ['chr1', '1', '100'])
    fn = pybedtools.BedTool._tmp()
    import pickle
    out = open(fn, 'w')
    pickle.dump(interval, out)
    out.close()
    new_interval = pickle.load(open(fn))
    assert str(interval) == str(new_interval)

    interval = pybedtools.create_interval_from_list(
        "chr2L	.	UTR	41	70	0	+	.	ID=mRNA:xs2:UTR:41-70;Parent=mRNA:xs2;".split('\t'))
    fn = pybedtools.BedTool._tmp()
    import pickle
    out = open(fn, 'w')
    pickle.dump(interval, out)
    out.close()
    new_interval = pickle.load(open(fn))
    assert str(interval) == str(new_interval)

def test_split():
    a = pybedtools.example_bedtool('a.bed')

    def func(x, dist1, dist2):
        "shift the features around"

        newstart = x.start + dist1
        newstop = x.stop + dist1
        x.start = newstart
        x.stop = newstop
        yield x

        x.start -= dist2
        x.stop -= dist2

        yield x

    result = str(a.split(func, 1000, 100))
    assert result == fix("""
    chr1	1001	1100	feature1	0	+
    chr1	901	1000	feature1	0	+
    chr1	1100	1200	feature2	0	+
    chr1	1000	1100	feature2	0	+
    chr1	1150	1500	feature3	0	-
    chr1	1050	1400	feature3	0	-
    chr1	1900	1950	feature4	0	+
    chr1	1800	1850	feature4	0	+
    """)

def test_additional_args():
    a = pybedtools.example_bedtool('a.bed')
    expected = fix("""
    chr1	1	2	1
    chr1	100	101	1
    chr1	900	901	1""")
    assert a.genome_coverage(bg=True, strand='+', g=dict(chr1=(1, 1000)), additional_args='-5') == expected

def test_tss():
    a = pybedtools.example_bedtool('a.bed')
    results = str(a.each(featurefuncs.TSS, upstream=3, downstream=5, add_to_name='_TSS'))
    print results
    assert results == fix("""
    chr1	0	6	feature1_TSS	0	+
    chr1	97	105	feature2_TSS	0	+
    chr1	495	503	feature3_TSS	0	-
    chr1	897	905	feature4_TSS	0	+
    """)

def test_extend_fields():
    a = pybedtools.example_bedtool('a.bed')
    results = str(a.each(featurefuncs.extend_fields, 8))
    print results
    assert results == fix("""
    chr1	1	100	feature1	0	+	.	.
    chr1	100	200	feature2	0	+	.	.
    chr1	150	500	feature3	0	-	.	.
    chr1	900	950	feature4	0	+	.	.
    """)

def test_gff2bed():
    a = pybedtools.example_bedtool('d.gff')
    results = str(a.each(featurefuncs.gff2bed, name_field='Parent'))
    assert results == fix("""
    chr1	49	300	.	.	+
    chr1	49	300	gene1	.	+
    chr1	74	150	mRNA1	.	+
    chr1	199	275	mRNA1	.	+
    chr1	1199	1275	.	.	+""")


    results = str(a.each(featurefuncs.gff2bed))
    assert results == fix("""
    chr1	49	300	gene1	.	+
    chr1	49	300	mRNA1	.	+
    chr1	74	150	CDS1	.	+
    chr1	199	275	CDS2	.	+
    chr1	1199	1275	rRNA1	.	+
    """)

    results = str(a.each(featurefuncs.gff2bed, name_field="nonexistent"))
    assert results == fix("""
    chr1	49	300	.	.	+
    chr1	49	300	.	.	+
    chr1	74	150	.	.	+
    chr1	199	275	.	.	+
    chr1	1199	1275	.	.	+
    """)

    results = str(a.each(featurefuncs.gff2bed, name_field=1))
    print results
    assert results == fix("""
    chr1	49	300	fake	.	+
    chr1	49	300	fake	.	+
    chr1	74	150	fake	.	+
    chr1	199	275	fake	.	+
    chr1	1199	1275	fake	.	+""")


def test_add_color():
    try:
        from matplotlib import cm
    except ImportError:
        print "matplotlib not installed; skipping test_add_color"
        return

    def modify_scores(f):
        fields = f.fields
        fields[4] = str(f[2])
        return pybedtools.create_interval_from_list(fields)
    a = pybedtools.example_bedtool('a.bed')
    a = a.each(modify_scores).saveas()
    cmap = cm.jet
    norm = a.colormap_normalize()
    results = str(a.each(featurefuncs.add_color, cmap=cmap, norm=norm))
    print results
    assert results == fix("""
    chr1	1	100	feature1	100	+	1	100	0,0,127
    chr1	100	200	feature2	200	+	100	200	0,0,255
    chr1	150	500	feature3	500	-	150	500	99,255,147
    chr1	900	950	feature4	950	+	900	950	127,0,0""")



#------------------------------------------------------------------------------
# Tests for IntervalFile, as accessed by BedTool objects
#------------------------------------------------------------------------------
def test_any_hits():
    a = pybedtools.example_bedtool('a.bed')

    assert 1 == a.any_hits(pybedtools.create_interval_from_list(
                      ['chr1', '900', '905', '.', '.', '-']))

    assert 0 == a.any_hits(pybedtools.create_interval_from_list(
                      ['chr1', '900', '905', '.', '.', '-']), same_strand=True)

    assert 0 == a.any_hits(pybedtools.create_interval_from_list(
                      ['chr1', '8000', '9000', '.', '.', '-']))

def test_all_hits():
    a = pybedtools.example_bedtool('a.bed')

    assert [a[2], a[3]] == a.all_hits(pybedtools.create_interval_from_list(
                      ['chr1', '450', '905', '.', '.', '-']))

    assert [a[2]] == a.all_hits(pybedtools.create_interval_from_list(
                      ['chr1', '450', '905', '.', '.', '-']), same_strand=True)

def test_count_hits():
    a = pybedtools.example_bedtool('a.bed')

    assert len(a.all_hits(pybedtools.create_interval_from_list(
                      ['chr1', '450', '905', '.', '.', '-']))) == 2

    assert len(a.all_hits(pybedtools.create_interval_from_list(
                      ['chr1', '450', '905', '.', '.', '-']), same_strand=True)) == 1

def test_multi_intersect():
    # Need to test here because "-i" is not a single other-bedtool like other
    # "-i" BEDTools programs, and this throws off the iter testing.
    a = pybedtools.example_bedtool('a.bed')
    b = pybedtools.example_bedtool('b.bed')
    x = pybedtools.BedTool()
    assert x.multi_intersect(i=[a.fn, b.fn]) == fix("""
        chr1	1	155	1	1	1	0
        chr1	155	200	2	1,2	1	1
        chr1	200	500	1	1	1	0
        chr1	800	900	1	2	0	1
        chr1	900	901	2	1,2	1	1
        chr1	901	950	1	1	1	0""")

    assert x.multi_intersect(i=[a.fn, b.fn], cluster=True) == fix("""
        chr1	155	200	2	1,2	1	1
        chr1	900	901	2	1,2	1	1""")

def test_union_bedgraphs():
    # from unionBedGraphs -examples...

    a = pybedtools.BedTool("""
    chr1  1000    1500    10
    chr1  2000    2100    20
    """, from_string=True)
    b = pybedtools.BedTool("""
    chr1  900 1600    60
    chr1  1700    2050    50
    """, from_string=True)
    c = pybedtools.BedTool("""
    chr1  1980    2070    80
    chr1  2090    2100    20
    """, from_string=True)

    x = pybedtools.BedTool()
    result = x.union_bedgraphs(i=[a.fn, b.fn, c.fn])
    assert result == fix("""
    chr1  900 1000    0   60  0
    chr1  1000    1500    10  60  0
    chr1  1500    1600    0   60  0
    chr1  1700    1980    0   50  0
    chr1  1980    2000    0   50  80
    chr1  2000    2050    20  50  80
    chr1  2050    2070    20  0   80
    chr1  2070    2090    20  0   0
    chr1  2090    2100    20  0   20
    """)

def test_window_maker():
    x = pybedtools.BedTool()
    a = pybedtools.example_bedtool('a.bed')
    result = x.window_maker(b=a.fn, w=50)
    print result
    assert result == fix("""
    chr1	1	51
    chr1	51	100
    chr1	100	150
    chr1	150	200
    chr1	150	200
    chr1	200	250
    chr1	250	300
    chr1	300	350
    chr1	350	400
    chr1	400	450
    chr1	450	500
    chr1	900	950
    """)

def test_random():
    a = pybedtools.BedTool()
    result = a.random(l=10, n=10, genome='hg19', seed=1)
    assert result == fix("""
    chr3	11945098	11945108	1	10	+
    chr15	84985693	84985703	2	10	-
    chr2	62691196	62691206	3	10	-
    chr18	18871346	18871356	4	10	+
    chr9	133374407	133374417	5	10	+
    chr9	48958184	48958194	6	10	+
    chrY	41568406	41568416	7	10	-
    chr4	16579517	16579527	8	10	+
    chr1	76589882	76589892	9	10	-
    chr3	55995799	55995809	10	10	-
    """)

def test_links():
    # have to be careful about the path, since it is embedded in the HTML
    # output -- so make a copy of the example file, and delete when done.
    os.system('cp %s a.links.bed' % pybedtools.example_filename('a.bed'))
    a = pybedtools.BedTool('a.links.bed')
    a = a.links()
    exp = open(pybedtools.example_filename('a.links.html')).read()
    obs = open(a.links_html).read()
    print exp
    print obs
    assert exp == obs
    os.unlink('a.links.bed')



def test_igv():
    a = pybedtools.example_bedtool('a.bed')
    a = a.igv()
    obs = open(a.igv_script).read()
    exp = open(pybedtools.example_filename('a.igv_script')).read()
    assert obs == exp

def test_bam_to_fastq():
    x = pybedtools.example_bedtool('small.bam')
    tmpfn = pybedtools.BedTool._tmp()
    y = x.bam_to_fastq(fq=tmpfn)
    assert open(y.fastq).read() == open(pybedtools.example_filename('small.fastq')).read()

def test_window():
    x = pybedtools.BedTool()
    z = x.window_maker(genome='hg19', w=100000)
    assert str(z[0]) == "chr1\t0\t100000\n"
    assert str(z[10000]) == 'chr16\t20800000\t20900000\n'

def test_gtf_gff_attrs():
    # smoke test.
    #
    # this has always worked:
    gff = ["chr1","fake","mRNA","51", "300",".", "+",".","ID=mRNA1;Parent=gene1;"]
    gff = pybedtools.create_interval_from_list(gff)
    gff.attrs

    # this previously failed because of the "=" in the attr string.
    gff = ['scaffold_52', 'Cufflinks', 'exon', '5478', '5568', '.', '+', '.', 'gene_id "XLOC_017766"; transcript_id "TCONS_00033979"; exon_number "6"; gene_name "g18412"; oId "PAC:26897502"; nearest_ref "PAC:26897502"; class_code "="; tss_id "TSS21210"; p_id "P18851";']
    gff = pybedtools.create_interval_from_list(gff)
    gff.attrs

    # TODO: is it necessary to support GFF vs GTF detection in this case:
    #
    #   GFF:
    #           class_code=" "
    #
    #   GTF:
    #           class_code "="


def test_jaccard():
    x = pybedtools.example_bedtool('a.bed')

    results = x.jaccard(pybedtools.example_bedtool('b.bed'))
    assert results == {'intersection': 46, 'union': 649, 'jaccard': 0.0708783, 'n_intersections': 2}, results

    results2 = x.jaccard(pybedtools.example_bedtool('b.bed'), stream=True)
    assert results == results2, results2

def test_reldist():
    x = pybedtools.example_bedtool('a.bed')
    results = x.reldist(pybedtools.example_bedtool('b.bed'))
    assert results == {'reldist': [0.15, 0.21, 0.28], 'count': [1, 1, 1], 'total': [3, 3, 3], 'fraction': [0.333, 0.333, 0.333]}, results

    results2 = x.reldist(pybedtools.example_bedtool('b.bed'), detail=True)
    print results2
    assert results2 == fix("""
    chr1	1	100	feature1	0	+	0.282
    chr1	100	200	feature2	0	+	0.153
    chr1	150	500	feature3	0	-	0.220""")
