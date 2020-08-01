#!/usr/bin/env python2

# fiximports.py -- Categorize imported transactions according to user-defined
#                  rules.
#
# Copyright (C) 2013 Sandeep Mukherjee <mukherjee.sandeep@gmail.com>
# Copyright (C) 2017 Jorge Javier Araya Navarro <jorge@esavara.cr>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# @file
#   @brief Categorize imported transactions according to user-defined rules.
#   @author Sandeep Mukherjee <mukherjee.sandeep@gmail.com>
#   @author Jorge Javier Araya Navarro <jorge@esavara.cr>
#
# This is a rules file for the fiximports script.  Lines beginning
# with a '#' are ignored. Blank lines are also ignored.  Each entry is
# in the format:
#
# Account	Pattern	Debit min.	Debit max.	Credit min.	Credit max.
#
# *** Each column is separated with a tab (not spaces). ***

# - Account is a colon(:) separated account path.
# - Pattern is a valid Python regexp.
# - Debit/Credit min/max is a number that express a range where
#   the amount of the transaction is within. They are optional and to
#   ignore a column you should put a 0 in it.
#
# Rules shouldn't have overlapping ranges or otherwise your rules may
# not work as expected, i.e.: the incorrect rule is being applied to a
# transaction but you expected the rule that follows it to be applied
# instead. Format is a search pattern. Example:
#
# Expenses:Supplies	Random Store	2500
#
# Specifies that a transaction beginning with "Random Store" starting
# at 2500 and up should go into the "Expenses:Supplies"
# account. Account names now can have spaces in them.

VERSION = "v1.0"

# python imports
import sys
import argparse
import logging
from datetime import date
from decimal import Decimal, DecimalException
import re

# gnucash imports
from gnucash import Session

# Account name, Pattern, debit min-max, credit min-max
matcher = re.compile(r"^([^\t\n\r\f\v]+)\t+([^\t\n\r\f\v]+)")
numbers = re.compile(r"(\d+((\.|,)\d+)?)\t?")


def account_from_path(top_account, account_path, original_path=None):
    """Get Account object by its path as `example:path`

    :param top_account: Account
    :param account_path: path expressed as ["example", "path"]
    :param original_path: Original path, optional.
    :returns: The Account referred by the `account_path`
    :rtype: gnucash.gnucash_core.Account

    """
    if original_path is None:
        original_path = account_path
    account, account_path = account_path[0], account_path[1:]
    account = top_account.lookup_by_name(account)
    if (account is None or account.get_instance() is None):
       logging.warning("path " + ''.join(original_path) + " could not be found")
       return None
    if len(account_path) > 0:
        return account_from_path(account, account_path, original_path)
    else:
        return account


def readrules(filename):
    """Read the rules file.
    """
    rules = []
    with open(filename, 'r') as fd:
        for line in fd:
            line = line.strip()
            if line and not line.startswith('#'):
                parsed = parserule(line)
                if parsed:
                    rules.append(parsed)
        else:
            return rules


def parserule(rule):
    """Parse a rule

    :param rule: string

    """
    result = []
    # Find the account name and the pattern
    match = matcher.match(rule)
    if match:
        ac = match.group(1)
        pattern = match.group(2)
        compiled = re.compile(pattern)  # Makesure RE is OK
        result.append(compiled)
        result.append(ac)
        # Find the min-max for debit and credit columns
        itermatch = numbers.finditer(rule, match.end(2))
        nrules = [Decimal(float(x.group(1).replace(",", ".")) * 100)
                  for x in itermatch]
        for x in range(1, 4 - len(nrules) + 1):
            nrules.append(None)
        # Sanitize mins and maxs
        dmin, dmax, cmin, cmax = nrules
        if dmin is None:
            dmin = Decimal(0)
        if dmax is None or dmax <= dmin:
            dmax = Decimal(sys.maxsize)
        if cmin is None:
            cmin = Decimal(0)
        if cmax is None or cmax <= cmin:
            cmax = Decimal(sys.maxsize)
        result.extend([dmin, dmax, cmin, cmax])
    else:
        logging.warn(
            'Ignoring line: (incorrect format): "%s"', rule)

    return result


def get_ac_from_str(concept, amount, rules, root_ac):
    """Check account and fix it if match with a rule.

    :param concept: Description of the account
    :param rules: the list of defined rules
    :param root_ac: an account from GNU Cash API
    :returns: The new path of the account
    :rtype: str or Account

    """
    for rule in rules:
        pattern, acpath, dmin, dmax, cmin, cmax = rule
        if pattern.search(concept):
            match = False
            # if negative, is a debit. If positive is a credit.
            if amount < 0:
                logging.debug("Is a debit: %s", concept)
                pamount = Decimal(amount * -1)
                match = pamount >= dmin and pamount <= dmax
            else:
                logging.debug("Is a credit: %s", concept)
                match = amount >= cmin and amount <= cmax

            if match:
                acplist = re.split(':', acpath)
                logging.debug('"%s" for %d matches pattern "%s":',
                              concept, amount, pattern.pattern)
                newac = account_from_path(root_ac, acplist)
                if newac is None:
                    logging.warning("Can't find account for path %s", acplist)
                    return ""
                return newac
    else:
        return ""


def parse_cmdline():
    """ Parses command-line arguments.

    Returns an array with all user-supplied values.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--imbalance-ac', default="Imbalance-[A-Z]{3}",
                        help="Imbalance account name pattern. Default=Imbalance-[A-Z]{3}")
    parser.add_argument('--version', action='store_true',
                        help="Display version and exit.")
    parser.add_argument('-m', '--use_memo', action='store_true',
                        help="Use memo field instead of description field to match rules.")
    parser.add_argument('-v', '--verbose', action='store_true',
                        help="Verbose (debug) logging.")
    parser.add_argument('-q', '--quiet', action='store_true',
                        help="Suppress normal output (except errors).")
    parser.add_argument('-n', '--nochange', action='store_true',
                        help="Do not modify gnucash file. No effect if using SQL.")
    parser.add_argument(
        "ac2fix", help="Full path of account to fix, e.g. Liabilities:CreditCard")
    parser.add_argument("rulesfile", help="Rules file. See doc for format.")
    parser.add_argument("gnucash_file", help="GnuCash file to modify.")
    args = parser.parse_args()

    return args


def get_transaction_info(split):
    """Return information and splits from a transaction

    :param split: The split from an account
    :returns: list of splits, date, description, memo and amount
    :rtype: list, date.datetime, string, string, Decimal

    """
    trans = split.parent
    splits = trans.GetSplitList()
    trans_date = trans.GetDate()
    trans_desc = trans.GetDescription()
    trans_memo = trans.GetNotes()
    trans_amount = Decimal(split.GetAmount().num())
    return splits, trans_date, trans_desc, trans_memo, trans_amount


def open_book(gnucashfile, account2fix):
    """Read a GNU Cash file

    :param gnucashfile: path to the GNU Cash file
    :param account2fix: list with the path of the account
    :returns: session object, root account and origin account
    :rtype:

    """
    gnucash_session = Session(gnucashfile, is_new=False)
    root_account = gnucash_session.book.get_root_account()
    orig_account = account_from_path(root_account, account2fix)
    return (gnucash_session, root_account, orig_account)


def fix_account(imbalance, root, origin, use_memo, rules):
    total = 0
    imbalance_total = 0
    fixed = 0
    imbalance_pattern = re.compile(imbalance)
    for split in origin.GetSplitList():
        total += 1
        # Get the transaction information
        splits, trans_date, trans_desc, trans_memo, trans_amount\
            = get_transaction_info(split)
        for split in splits:
            acname = split.GetAccount().GetName()
            logging.debug('%s: %s => %s', trans_date, trans_desc, acname)
            if imbalance_pattern.match(acname):
                imbalance_total += 1
                # Use the transaction description to match the rule pattern
                search_str = trans_desc
                if use_memo:
                    # Use the memo field instead of the transaction
                    # description
                    search_str = trans_memo
                # Calculate the transaction's new account
                newac = get_ac_from_str(search_str, trans_amount,
                                        rules, root)

                # Check if transaction should be moved
                if newac != "":
                    logging.debug(
                        '\tChanging account to: %s', newac.GetName())
                    # Move the transaction to a new account
                    split.SetAccount(newac)
                    fixed += 1
    else:
        return (total, imbalance_total, fixed)

# Main entry point.
# 1. Parse command line.
# 2. Read rules.
# 3. Create session.
# 4. Get a list of all splits in the account to be fixed. For every split:
#     4.1: Lookup up description or memo field.
#     4.2: Use the rules to check if a matching account can be located.
#     4.3: If there is a matching account, set the account in the split.
# 5. Print stats and save the session (if needed).


def main():
    args = parse_cmdline()
    if args.version:
        print(VERSION)
        exit(0)

    if args.verbose:
        loglevel = logging.DEBUG
    elif args.quiet:
        loglevel = logging.WARN
    else:
        loglevel = logging.INFO
    logging.basicConfig(level=loglevel)

    rules = readrules(args.rulesfile)
    account_path = re.split(':', args.ac2fix)
    session, root, origin = open_book(args.gnucash_file, account_path)
    total, imbalance, fixed = fix_account(
        args.imbalance_ac, root, origin, args.use_memo, rules)
    if not args.nochange:
        session.save()
    session.end()
    logging.info('Total splits=%s, imbalance=%s, fixed=%s',
                 total, imbalance, fixed)


if __name__ == "__main__":
    main()
