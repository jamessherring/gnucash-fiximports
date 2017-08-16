from nose import with_setup
import glob
import os
import shutil
from fiximports import parserule, fix_account, open_book
import re


rawrules = ["Expenses:Dining	PIZZA",
            "Income:Salary	Salary",
            "Expenses:Dining	Random Store	0	10",
            "Expenses:Supplies	Random Store	200	300"]

originpath = ["Assets", "Current Assets", "Checking Account"]
bookpath = "test/fixtures/sample.gnucash"
testbookpath = "test/fixtures/sample-test.gnucash"


def setup():
    try:
        os.remove(testbookpath)
    except:
        pass
    # copy the original sample.gnucash file into sample-test.gnucash
    shutil.copyfile(bookpath, testbookpath)


def tearDown():
    # Delete all LCK files of the GNU Cash file
    filelist = glob.glob("test/fixtures/*.LCK")
    filelist.extend(glob.glob("test/fixtures/*.LNK"))
    filelist.extend(glob.glob("test/fixtures/*.gnucash.*.*"))
    for f in filelist:
        os.remove(f)


def testParser():
    for rule in rawrules:
        result = parserule(rule)
        assert result != [], "Parser failed to parse rule: {}".format(rule)


def testParserInvalid():
    result = parserule("Example:Invalid")  # Lacks of rule
    assert result == [], "Parser should not parse rule: Example:Invalid"


@with_setup(setup, tearDown)
def testFixing():
    session, root, origin = open_book(testbookpath, originpath)
    total, imb, fix = fix_account(r"Imbalance-[A-Z]{3}", root, origin, False,
                                  [parserule(rule) for rule in rawrules])
    session.save()
    session.end()
