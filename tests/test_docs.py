##
# Copyright (c) 2017-present MagicStack Inc.
# All rights reserved.
#
# See LICENSE for details.
##


import collections
import contextlib
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest

try:
    import docutils.nodes
    import docutils.parsers
    import docutils.utils
    import docutils.frontend
    import docutils.parsers.rst.directives.body  # type: ignore
    from edb.tools.docs.shared import make_CodeBlock

    docutils.parsers.rst.directives.register_directive(
        'code-block',
        make_CodeBlock(docutils.parsers.rst.directives.body.CodeBlock)
    )
except ImportError:
    docutils = None  # type: ignore

try:
    import sphinx
except ImportError:
    sphinx = None  # type: ignore

from graphql.language import parser as graphql_parser

from edb.edgeql import parser as ql_parser


def find_edgedb_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class LintControl:

    _filename: str | None
    _errors: list[str]

    def __init__(self):
        self._lint_on = True
        self._line_no = 0
        self._errors = []

    @contextlib.contextmanager
    def enter_file(self, filename: str):
        self._filename = filename
        self._line_no = 0
        self._lint_on = True

        try:
            yield
        finally:
            try:
                if not self._lint_on:
                    raise AssertionError(
                        f"Unexpected EOF. No closing '.. lint-on' found in "
                        f"{self._filename}")
            finally:
                self._filename = None

    @property
    def filename(self) -> str:
        assert self._filename is not None
        return self._filename

    def feed_line(self, line: str):
        assert self._filename is not None
        self._line_no += 1

        if line.startswith('.. lint-off'):
            if self._lint_on:
                self._lint_on = False
            else:
                raise AssertionError(
                    f'Mismatched lint-on/lint-off in '
                    f'{self._filename}, line {self._line_no}'
                )
        elif line.startswith('.. lint-on'):
            if not self._lint_on:
                self._lint_on = True
            else:
                raise AssertionError(
                    f'Mismatched lint-on/lint-off in '
                    f'{self._filename}, line {self._line_no}'
                )

    def report_error(self, message: str):
        self._errors.append(f'{self._filename}:{self._line_no}: {message}')

    def raise_errors_if_any(self):
        if self._errors:
            raise AssertionError(
                '\n'.join(self._errors)
            )

    def is_linting(self):
        return self._lint_on

    def __enter__(self):
        return self

    def __exit__(self, _et, _ev, _tb):
        pass


class TestDocSnippets(unittest.TestCase):
    """Lint and validate EdgeDB documentation files.

    Checks:

    * all source code in "code-block" directives is parsed to
      check that the syntax is valid;

    * any ReST warnings (like improper headers or broken indentation)
      are reported as errors.
    """

    CodeSnippet = collections.namedtuple(
        'CodeSnippet',
        ['filename', 'lineno', 'lang', 'code'])

    class RestructuredTextStyleError(Exception):
        pass

    if docutils is not None:
        class CustomDocutilsReporter(docutils.utils.Reporter):

            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.lint_errors = set()

            def system_message(self, level, message, *children, **kwargs):
                skip = (
                    message.startswith('Unknown interpreted text role') or
                    message.startswith('No role entry for') or
                    message.startswith('Unknown directive type') or
                    message.startswith('No directive entry for') or
                    level < 2  # Ignore DEBUG and INFO messages.
                )

                msg = super().system_message(
                    level, message, *children, **kwargs)

                if not skip:
                    self.lint_errors.add(
                        f"{message} at {msg['source']} on line "
                        f"{msg.get('line', '?')}")

                return msg

    def find_rest_files(self, path: str) -> list[str]:
        def scan(path):
            with os.scandir(path) as it:
                for entry in it:
                    if entry.is_file() and entry.name.endswith('.rst'):
                        files.append(entry.path)
                    if entry.is_dir():
                        scan(entry.path)

        files: list[str] = []
        scan(path)
        return files

    def extract_code_blocks(self, source: str, filename: str):
        blocks = []

        parser_class = docutils.parsers.get_parser_class('rst')
        parser = parser_class()

        settings = docutils.frontend.OptionParser(
            components=(parser_class, )).get_default_values()
        settings.syntax_highlight = 'none'

        min_error_code = 100  # Ignore all errors, we process them manually.
        reporter = self.CustomDocutilsReporter(
            filename, min_error_code, min_error_code)
        document = docutils.nodes.document(settings, reporter, source=filename)
        document.note_source(filename, -1)

        parser.parse(source, document)

        if reporter.lint_errors:
            raise self.RestructuredTextStyleError(
                '\n\nRestructuredText lint errors:\n' +
                '\n'.join(reporter.lint_errors))

        directives = []
        for node in document.traverse():
            if node.tagname == 'literal_block':
                if 'code' in node.attributes['classes']:
                    directives.append(node)

                else:
                    block = node.astext()

                    # certain literal blocks also contain code-blocks
                    if re.match(r'^\.\. eql:(operator|function|constraint)::',
                                block):

                        # figure out the line offset of the start of the block
                        node_parent = node
                        while node_parent and node_parent.line is None:
                            node_parent = node_parent.parent
                        if node_parent:
                            node_parent_line = \
                                node_parent.line - block.count('\n')
                        else:
                            node_parent_line = 0

                        subdoc = docutils.nodes.document(
                            settings, reporter, source=filename)
                        subdoc.note_source(filename, node_parent_line)

                        # cut off the first chunk
                        block = block.split('\n\n', maxsplit=1)[1]
                        # dedent the rest
                        block = textwrap.dedent(block)

                        parser.parse(block, subdoc)

                        subdirs = subdoc.traverse(
                            condition=lambda node: (
                                node.tagname == 'literal_block' and
                                'code' in node.attributes['classes'])
                        )
                        for subdir in subdirs:
                            if subdir.line is not None:
                                subdir.line += node_parent_line
                            directives.append(subdir)

        for directive in directives:
            classes = directive.attributes['classes']

            if len(classes) < 2 or classes[0] != 'code':
                continue

            lang = directive.attributes['classes'][1]
            code = directive.astext()

            lineno = directive.line
            if lineno is None:
                # Some docutils blocks (like tables) do not support
                # line numbers, so we try to traverse the parent tree
                # to find the nearest block with a line number.
                parent_directive = directive
                while parent_directive and parent_directive.line is None:
                    parent_directive = parent_directive.parent
                if parent_directive and parent_directive.line is not None:
                    lineno = parent_directive.line
            else:
                lineno = lineno

            blocks.append(self.CodeSnippet(filename, str(lineno), lang, code))

        return blocks

    def extract_snippets_from_repl(self, replblock):
        in_query = False
        snips = []
        for line in replblock.split('\n'):
            if not in_query:
                m = re.match(r'(?P<p>[\w\[:\]>]+>\s)(?P<l>.*)', line)
                if m:
                    # >>> prompt
                    in_query = True
                    snips.append(
                        (len(m.group('p')), [])
                    )
                    snips[len(snips) - 1][1].append(m.group('l'))
                else:
                    # output
                    if not snips:
                        raise AssertionError(
                            f'invalid REPL block (starts with output); '
                            f'offending line {line!r}')
            else:
                # ... prompt?
                m = re.match(r'(?P<p>\.+\s)(?P<l>.*)', line)
                if m:
                    # yes, it's "... " line
                    if not snips:
                        raise AssertionError(
                            f'invalid REPL block (... before >>>); '
                            f'offending line {line!r}')
                    if len(m.group('p')) != snips[len(snips) - 1][0]:
                        raise AssertionError(
                            f'invalid REPL block: number of "." does not '
                            f'match number of ">"; '
                            f'offending line {line!r}')
                    snips[len(snips) - 1][1].append(m.group('l'))
                else:
                    # no, this is output
                    in_query = False

        return ['\n'.join(s[1]) for s in snips
                # ignore the "\c" and other REPL commands
                if not re.match(r'\\\w+', s[1][0])]

    def run_block_test(self, block):
        try:
            lang = block.lang
            expect_invalid = False

            if lang.endswith('-repl'):
                lang = lang.rpartition('-')[0]
                code = self.extract_snippets_from_repl(block.code)
            elif lang.endswith('-diff'):
                # In the diff block we need to truncate "-"/"+" at the
                # beginning of each line. We will make two copies of
                # the code as the before and after version. Both will
                # be validated.
                before = []
                after = []
                for line in block.code.split('\n'):

                    if line == "":
                        continue

                    first = line.strip()[0]
                    if first == '-':
                        before.append(line[1:])
                    elif first == '+':
                        after.append(line[1:])
                    else:
                        before.append(line[1:])
                        after.append(line[1:])

                code = ['\n'.join(before), '\n'.join(after)]
                # truncate the "-diff" from the language
                lang = lang[:-5]
            else:
                code = [block.code]

            if lang.endswith('-invalid'):
                lang = lang[:-8]
                expect_invalid = True

            try:
                for snippet in code:
                    if lang == 'edgeql':
                        ql_parser.parse_block(snippet)
                    elif lang == 'sdl':
                        # Strip all the "using extension ..." and comment
                        # lines as they interfere with our module
                        # detection.
                        sdl = re.sub(
                            r'(using\s+extension\s+\w+;)|(#.*?\n)',
                            '',
                            snippet
                        ).strip()

                        # the snippet itself may either contain a module
                        # block or have a fully-qualified top-level name
                        if not sdl or re.match(
                                r'''(?xm)
                                    (\bmodule\s+\w+\s*{) |
                                    (^.*
                                        (type|annotation|link|property|constraint)
                                        \s+(\w+::\w+)\s+
                                        ({|extending)
                                    )
                                ''',
                                sdl):
                            ql_parser.parse_sdl(snippet)
                        else:
                            ql_parser.parse_sdl(
                                f'module default {{ {snippet} }}'
                            )
                    elif lang == 'edgeql-result':
                        # REPL results
                        pass
                    elif lang == 'pseudo-eql':
                        # Skip "pseudo-eql" language as we don't have a
                        # parser for it.
                        pass
                    elif lang == 'graphql':
                        graphql_parser.parse(snippet)
                    elif lang == 'graphql-schema':
                        # The graphql-schema can be highlighted using graphql
                        # lexer, but it does not have a dedicated parser.
                        pass
                    elif lang == 'json':
                        json.loads(snippet)
                    elif lang in {
                        'bash',
                        'powershell',
                        'shell',
                        'c',
                        'javascript',
                        'python',
                        'typescript',
                        'go',
                        'yaml',
                        'text',
                        'jsx',
                        'rust',
                        'tsx',
                        'elixir',
                        'toml',
                        'sql',
                        'dockerfile'
                    }:
                        pass
                    elif lang[-5:] == '-diff':
                        pass
                    else:
                        raise LookupError(f'unknown code-lang {lang}')
            except LookupError as ex:
                raise ex
            except Exception as ex:
                if not expect_invalid:
                    raise ex
            else:
                if expect_invalid:
                    raise AssertionError("code block is marked with '-invalid'"
                                         " lang, but did not fail validation")
        except Exception as ex:
            raise AssertionError(
                f'unable to parse {block.lang} code block in '
                f'{block.filename}, around line {block.lineno}: '
                f'{code}') from ex

    @unittest.skipIf(docutils is None, 'docutils is missing')
    def test_cqa_doc_snippets(self):
        edgepath = edgepath = find_edgedb_root()
        docspath = os.path.join(edgepath, 'docs')

        for filename in self.find_rest_files(docspath):
            with open(filename, 'rt') as f:
                source = f.read()

            blocks = self.extract_code_blocks(source, filename)

            for block in blocks:
                self.run_block_test(block)

    def test_cqa_doc_trailing_whitespace(self):
        edgepath = find_edgedb_root()
        docspath = os.path.join(edgepath, 'docs')

        ws_errors = collections.defaultdict(set)

        for filename in self.find_rest_files(docspath):
            with open(filename, 'rt') as f:
                source = f.readlines()

            for lineno, line in enumerate(source):
                if re.match(r'\s+\n$', line):
                    ws_errors[filename].add(lineno)

        if ws_errors:
            raise AssertionError(
                'trailing whitespace:\n\n' +
                '\n'.join(
                    f'{filename}:{linenos!r}'
                    for filename, linenos in ws_errors.items()
                )
            )

    def test_cqa_doc_substitutions(self):
        edgepath = find_edgedb_root()
        docspath = os.path.join(edgepath, 'docs')

        with LintControl() as lc:
            for filename in self.find_rest_files(docspath):
                if '/docs/resources/changelog/' in filename:
                    # changelog files contain a bunch of historical
                    # text that sometimes can't use the new stuff.
                    continue

                with lc.enter_file(filename):
                    with open(filename, 'rt') as f:
                        source = f.readlines()

                    for line in source:
                        lc.feed_line(line)

                        if not lc.is_linting():
                            continue

                        if '``edgedb://' in line:
                            lc.report_error(
                                f'do not use ``edgedb://``, '
                                f'use |geluri| for "gel://" and '
                                f':geluri:`blah` for "gel://blah"')
                        if '``gel://' in line:
                            lc.report_error(
                                f'do not use ``gel://``, '
                                f'use |geluri| for "gel://" and '
                                f':geluri:`blah` for "gel://blah"')

                        if '.esdl``' in line or '.gel``' in line:
                            lc.report_error(
                                f"don't use ``filename.esdl`` "
                                f"or ``filename.gel``, use :dotgel:`filename` "
                                f"instead")
                        if '``gel ' in line:
                            lc.report_error(
                                f'do not use ``gel`` markup '
                                f'for "gel" cli commands, '
                                f'use :gelcmd:`command` instead; '
                                f'it will be rendered as ``gel command``')
                        if '``edgedb ' in line:
                            lc.report_error(
                                f'do not use ``edgedb`` markup '
                                f'for "gel" cli commands, '
                                f'use :gelcmd:`command` instead; '
                                f'it will be rendered as ``gel command``')

        lc.raise_errors_if_any()

    @unittest.skipIf(docutils is None, 'docutils is missing')
    def test_doc_test_broken_code_block_01(self):
        source = '''
        In large applications, the schema will usually be split
        into several :ref:`modules<ref_schema_evolution_modules>`.

        .. code-block:: edgeql

            SELECT 122 + foo();

        A *schema module* defines the effective namespace for
        elements it defines.

        .. code-block:: edgeql

            SELECT 42;
            # ^ expected to return 42
            SELECT foo(

        Schema modules can import other modules to use schema
        elements they define.
        '''

        blocks = self.extract_code_blocks(source, '<test>')
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0].code, 'SELECT 122 + foo();')
        self.run_block_test(blocks[0])

        with self.assertRaisesRegex(AssertionError, 'unable to parse edgeql'):
            self.run_block_test(blocks[1])

    @unittest.skipIf(docutils is None, 'docutils is missing')
    def test_doc_test_broken_code_block_02(self):
        source = r'''
        String operator with a buggy example.

        .. eql:operator:: LIKE: str LIKE str -> bool
                                str NOT LIKE str -> bool

            Case-sensitive simple string matching.

            Example:

            .. code-block:: edgeql-repl

                db> SELECT 'a%%c' NOT LIKE 'a\%c';
                {true}
        '''

        blocks = self.extract_code_blocks(source, '<test>')
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].code,
                         "db> SELECT 'a%%c' NOT LIKE 'a\\%c';\n{true}")

        with self.assertRaisesRegex(AssertionError, 'unable to parse edgeql'):
            self.run_block_test(blocks[0])

    @unittest.skipIf(docutils is None, 'docutils is missing')
    def test_doc_test_bad_header(self):
        source = textwrap.dedent('''
            Section
            -----

            aaa aaa aaa
        ''')

        with self.assertRaisesRegex(
                self.RestructuredTextStyleError,
                r'lint errors:[.\s]*Title underline too short'):
            self.extract_code_blocks(source, '<test>')

    @unittest.skipIf(sphinx is None, 'sphinx is missing')
    def test_doc_full_build(self):
        docs_root = os.path.join(find_edgedb_root(), 'docs')

        with tempfile.TemporaryDirectory() as td:
            proc = subprocess.run(
                [
                    sys.executable,
                    '-m', 'sphinx',
                    '-n',
                    '-b', 'xml',
                    '-q',
                    '-D', 'master_doc=index',
                    '-W',
                    docs_root,
                    td,
                ],
                text=True,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
            )

        if proc.returncode:
            raise AssertionError(
                f'Unable to build docs with Sphinx.\n\n'
                f'STDOUT:\n{proc.stdout}\n\n'
                f'STDERR:\n{proc.stderr}\n'
            )

        errors = []
        ignored_errors = re.compile(
            r'^.* WARNING: undefined label: edgedb-'
            r'(python|js|go|dart|dotnet|elixir|java)-.*$'
        )
        for line in proc.stderr.splitlines():
            if not ignored_errors.match(line):
                errors.append(line)

        if len(errors) > 0:
            errors = '\n'.join(errors)
            raise AssertionError(
                f'Unable to build docs with Sphinx.\n\n'
                f'{errors}\n\n'
            )
