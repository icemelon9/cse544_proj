#!/usr/bin/python
#
# Taesoo Kim
#
# Original License:
#
#   This file is part of Rubber and thus covered by the GPL
#   (c) Emmanuel Beffara, 2002--2006
#   Modified by Olivier Verdier <olivier.verdier@gmail.com>

import os
import re
import sys

# The function `_' is defined here to prepare for internationalization.
def _ (txt): return txt

re_loghead    = re.compile("This is [0-9a-zA-Z-]*(TeX|Omega)")
re_rerun      = re.compile("LaTeX Warning:.*Rerun")
re_file       = re.compile("(\\((?P<file>[^ \n\t(){}]*)|\\))")
re_badbox     = re.compile(r"(Ov|Und)erfull \\[hv]box ")
re_line       = re.compile(r"(l\.(?P<line>[0-9]+)( (?P<code>.*))?$|<\*>)")
re_cseq       = re.compile(r".*(?P<seq>\\[^ ]*) ?$")
re_page       = re.compile("\[(?P<num>[0-9]+)\]")
re_atline     = re.compile("( detected| in paragraph)? at lines? (?P<line>[0-9]*)(--(?P<last>[0-9]*))?")
re_reference  = re.compile("LaTeX Warning: Reference `(?P<ref>.*)' on page (?P<page>[0-9]*) undefined on input line (?P<line>[0-9]*)\\.$")
re_citation   = re.compile("^.*Citation `(?P<cite>.*)' on page (?P<page>[0-9]*) undefined on input line (?P<line>[0-9]*)\\.$")
re_label      = re.compile("LaTeX Warning: (?P<text>Label .*)$")
re_warning    = re.compile("(LaTeX|Package)( (?P<pkg>.*))? Warning: (?P<text>.*)$")
re_online     = re.compile("(; reported)? on input line (?P<line>[0-9]*)")
re_ignored    = re.compile("; all text was ignored after line (?P<line>[0-9]*).$")

class LogCheck (object):
    """
    This class performs all the extraction of information from the log file.
    For efficiency, the instances contain the whole file as a list of strings
    so that it can be read several times with no disk access.
    """
    #-- Initialization {{{2

    def __init__ (self):
        self.lines = None

    def read (self, name):
        """
        Read the specified log file, checking that it was produced by the
        right compiler. Returns true if the log file is invalid or does not
        exist.
        """
        self.lines = None
        with open(name) as file:
            line = file.readline()
            if not line:
                file.close()
                raise ValueError("Empty file")
            if not re_loghead.match(line):
                file.close()
                raise ValueError("This doesn't seem to be a tex log file")
            self.lines = file.readlines()

    #-- Process information {{{2

    def errors (self):
        """
        Returns true if there was an error during the compilation.
        """
        skipping = 0
        for line in self.lines:
            if line.strip() == "":
                skipping = 0
                continue
            if skipping:
                continue
            m = re_badbox.match(line)
            if m:
                skipping = 1
                continue
            if line[0] == "!":
                # We check for the substring "pdfTeX warning" because pdfTeX
                # sometimes issues warnings (like undefined references) in the
                # form of errors...

                if "pdfTeX warning" in line:
                    return True
        return False

    def run_needed (self):
        """
        Returns true if LaTeX indicated that another compilation is needed.
        """
        for line in self.lines:
            if re_rerun.match(line):
                return True
        return False

    #-- Information extraction {{{2

    def continued (self, line):
        """
        Check if a line in the log is continued on the next line. This is
        needed because TeX breaks messages at 79 characters per line. We make
        this into a method because the test is slightly different in Metapost.
        """
        return len(line) == 79 and line[-3:] != '...'

    def parse (self, errors=False, boxes=False, refs=False, warnings=False):
        """
        Parse the log file for relevant information. The named arguments are
        booleans that indicate which information should be extracted:
        - errors: all errors
        - boxes: bad boxes
        - refs: warnings about references
        - warnings: all other warnings
        The function returns a generator. Each generated item is a dictionary
        that contains (some of) the following entries:
        - kind: the kind of information ("error", "box", "ref", "warning")
        - text: the text of the error or warning
        - code: the piece of code that caused an error
        - file, line, last, pkg: as used by Message.format_pos.
        """
        if not self.lines:
            return
        last_file = None
        pos = [last_file]
        page = 1
        parsing = False   # True if we are parsing an error's text
        skipping = False  # True if we are skipping text until an empty line
        something = False # True if some error was found
        prefix = None  # the prefix for warning messages from packages
        accu = ""      # accumulated text from the previous line
        for line in self.lines:
            line = line[:-1]  # remove the line feed

            # TeX breaks messages at 79 characters, just to make parsing
            # trickier...

            if self.continued(line):
                accu += line
                continue
            line = accu + line
            accu = ""

            # Text that should be skipped (from bad box messages)

            if prefix is None and line == "":
                skipping = False
                continue

            if skipping:
                continue

            # Errors (including aborted compilation)

            if parsing:
                if error == "Undefined control sequence.":
                    # This is a special case in order to report which control
                    # sequence is undefined.
                    m = re_cseq.match(line)
                    if m:
                        error = "Undefined control sequence %s." % m.group("seq")
                m = re_line.match(line)
                if m:
                    parsing = False
                    skipping = True
                    pdfTeX = "pdfTeX warning" in line
                    if (pdfTeX and warnings) or (errors and not pdfTeX):
                        if pdfTeX:
                            d = {
                                "kind": "warning",
                                "pkg": "pdfTeX",
                                "text": error[error.find(":")+2:]
                            }
                        else:
                            d = {
                                "kind": "error",
                                "text": error
                            }
                        d.update( m.groupdict() )
                        m = re_ignored.search(error)
                        if m:
                            d["file"] = last_file
                            if d.has_key("code"):
                                del d["code"]
                            d.update( m.groupdict() )
                        elif pos[-1] is None:
                            d["file"] = last_file
                        else:
                            d["file"] = pos[-1]
                        yield d
                elif line[0] == "!":
                    error = line[2:]
                elif line[0:3] == "***":
                    parsing = False
                    skipping = True
                    if errors:
                        yield   {
                            "kind": "abort",
                            "text": error,
                            "why" : line[4:],
                            "file": last_file
                            }
                elif line[0:15] == "Type X to quit ":
                    parsing = False
                    skipping = False
                    if errors:
                        yield   {
                            "kind": "error",
                            "text": error,
                            "file": pos[-1]
                            }
                continue

            if len(line) > 0 and line[0] == "!":
                error = line[2:]
                parsing = True
                continue

            if line == "Runaway argument?":
                error = line
                parsing = True
                continue

            # Long warnings

            if prefix is not None:
                if line[:len(prefix)] == prefix:
                    text.append(line[len(prefix):].strip())
                else:
                    text = " ".join(text)
                    m = re_online.search(text)
                    if m:
                        info["line"] = m.group("line")
                        text = text[:m.start()] + text[m.end():]
                    if warnings:
                        info["text"] = text
                        d = { "kind": "warning" }
                        d.update( info )
                        yield d
                    prefix = None
                continue

            # Undefined references

            m = re_reference.match(line)
            if m:
                if refs:
                    d = {
                        "kind": "warning",
                        "text": _("Reference `%s' undefined.") % m.group("ref"),
                        "file": pos[-1]
                        }
                    d.update( m.groupdict() )
                    yield d
                continue

            m = re_citation.match(line)
            if m:
                if refs:
                    d = {
                        "kind": "warning",
                        "text": _("Citation `%s' undefined.") % m.group("cite"),
                        "file": pos[-1]
                        }
                    d.update( m.groupdict() )
                    yield d
                continue

            m = re_label.match(line)
            if m:
                if refs:
                    d = {
                        "kind": "warning",
                        "file": pos[-1]
                        }
                    d.update( m.groupdict() )
                    yield d
                continue

            # Other warnings

            if line.find("Warning") != -1:
                m = re_warning.match(line)
                if m:
                    info = m.groupdict()
                    info["file"] = pos[-1]
                    info["page"] = page
                    if info["pkg"] is None:
                        del info["pkg"]
                        prefix = ""
                    else:
                        prefix = ("(%s)" % info["pkg"])
                    prefix = prefix.ljust(m.start("text"))
                    text = [info["text"]]
                continue

            # Bad box messages

            m = re_badbox.match(line)
            if m:
                if boxes:
                    mpos = { "file": pos[-1], "page": page }
                    m = re_atline.search(line)
                    if m:
                        md = m.groupdict()
                        for key in "line", "last":
                            if md[key]: mpos[key] = md[key]
                        line = line[:m.start()]
                    d = {
                        "kind": "warning",
                        "text": line
                        }
                    d.update( mpos )
                    yield d
                skipping = True
                continue

            # If there is no message, track source names and page numbers.

            last_file = self.update_file(line, pos, last_file)
            page = self.update_page(line, page)

    def get_errors (self):
        return self.parse(errors=True)
    def get_boxes (self):
        return self.parse(boxes=True)
    def get_references (self):
        return self.parse(refs=True)
    def get_warnings (self):
        return self.parse(warnings=True)

    def update_file (self, line, stack, last):
        """
        Parse the given line of log file for file openings and closings and
        update the list `stack'. Newly opened files are at the end, therefore
        stack[1] is the main source while stack[-1] is the current one. The
        first element, stack[0], contains the value None for errors that may
        happen outside the source. Return the last file from which text was
        read (the new stack top, or the one before the last closing
        parenthesis).
        """
        m = re_file.search(line)
        while m:
            if line[m.start()] == '(':
                last = m.group("file")
                stack.append(last)
            else:
                last = stack[-1]
                del stack[-1]
            line = line[m.end():]
            m = re_file.search(line)
        return last

    def update_page (self, line, before):
        """
        Parse the given line and return the number of the page that is being
        built after that line, assuming the current page before the line was
        `before'.
        """
        ms = re_page.findall(line)
        if ms == []:
            return before
        return int(ms[-1]) + 1

biberrs = ["I was expecting", " : ", "(Error"]
def search_blg(pn):
    found = False
    (fn, ext) = os.path.splitext(pn)
    with open(fn + ".blg") as fd:
        for l in fd:
            if any(l.startswith(t) for t in biberrs):
                print(" > " + l.rstrip())
                found = True
    return found

if __name__ == '__main__':
    if len(sys.argv) == 2:
        args = sys.argv[1:]
    else:
        args = ["/dev/stdin"]

    found = False
    for pn in args:
        parser = LogCheck()
        parser.read(pn)
        errs = list(parser.get_errors())
        for e in errs:
            found = True
            if "line" not in e:
                e["line"] = "-"
            print("{file}:{line}:\033[0;31m{kind}\033[0m:{text}".format(**e))
            if "code" in e:
                print("> {code}".format(**e))

    # speculate .blg
    if not found:
        for pn in args:
            found |= search_blg(pn)

    exit(0 if found else 1)