import string
import logging

from PyQt4.QtCore import QFileInfo

import organica.utils.helpers as helpers


logger = logging.getLogger(__name__)


class ParseError(Exception):
    pass


class FormatStringToken:
    def __init__(self):
        self.start = 0
        self.length = 0
        self.isBlock = False
        self.value = ''
        self.params = {}

    def getParam(self, key, default=None):
        return self.params[key][0] if key in self.params else default


class _FormatStringParser:
    """Some object {tag_name: max_items = '', ellipsis = ''}

    block = block_name [: param_list]
    block_name = (alpha|"_"|"@") {alpha|digit|"_"}
    ident = (alpha|"_") {alpha|digit|"_"}
    param_list = param {, param}
    param = ident ["=" value]
    value = ("\"" {*} "\"") | ("'" {*} "'") | (alpha|digit|"_") {alpha|digit|"_"}
    """

    def __init__(self):
        self.__tokens = []
        self.__tail, self.__head = 0, 0
        self.text = ''
        self.__parsed = False

    @property
    def tokens(self):
        if not self.__parsed:
            self.parse()
        return self.__tokens

    def parse(self, text):
        self.text = text
        self.__head = self.__tail = 0
        self.__tokens = []

        while True:
            if self.__isEnd():
                break

            self.__ctoken = FormatStringToken()
            self.__tail = self.__head
            if self.__getChar() == '{':
                self.__ctoken.isBlock = True
                self.__ctoken.start = self.__head
                self.__head += 1
                self.__eatWhitespace()
                self.__ctoken.value = self.__getIdent(is_block_name=True)
                if not self.__ctoken.value:
                    raise ParseError('block name expected in format string "{0}" at position {1}' \
                                    .format(self.text, self.__head))

                self.__eatWhitespace()
                if self.__getChar() == ':':
                    self.__head += 1
                    self.__ctoken.params = self.__getParams()
                    self.__eatWhitespace()

                if self.__getChar() != '}':
                    raise ParseError('end of block expected in format string "{0}" at position {1}' \
                                     .format(self.text, self.__head))
                self.__head += 1

                self.__ctoken.length = self.__head - self.__ctoken.start
            else:
                self.__ctoken.isBlock = False
                self.__ctoken.start = self.__head
                while not self.__isEnd() and self.__getChar() != '{':
                    if self.__getChar() == '\\':
                        self.__head += 1
                    self.__head += 1
                self.__ctoken.value = self.__processEscapes(self.text[self.__tail:self.__head])
                self.__ctoken.length = self.__head - self.__ctoken.start
            self.__tokens.append(self.__ctoken)
        self.__parsed = True

    @staticmethod
    def buildFromTokens(tokens):
        built = ''
        for token in tokens:
            if not token.isBlock:
                # but it can differ from real user input (as it could escape another chars)
                built += (helpers.escape(token.value, '{\\'))
            else:
                built += '{' + token.value
                if token.params:
                    built += ': '
                    need_comma = False
                    for param_name in token.params:
                        param_value = token.params[param_name][0]
                        quote_type = token.params[param_name][1]
                        if not need_comma:
                            need_comma = True
                        else:
                            built += ', '

                        if param_value is None:
                            built += param_name
                        elif isinstance(param_value, str):
                            built += '{0}={2}{1}{2}'.format(param_name,
                                                              helpers.escape(param_value, '"\\'),
                                                              quote_type)
                        elif isinstance(param_value, int):
                            built += '{0}={1}'.format(param_name, param_value)
                        else:
                            raise TypeError('unexpected type for parameter value: {0}' \
                                            .format(type(param_value)))
                built += '}'
        return built

    def __getChar(self):
        return self.text[self.__head] if self.__head < len(self.text) else '\0'

    def __isEnd(self):
        return self.__head >= len(self.text)

    def __getIdent(self, is_block_name=False):
        self.__eatWhitespace()
        c = self.__getChar()
        if c in string.ascii_letters or c == '_' or (is_block_name and c == '@'):
            self.__head += 1
            while not self.__isEnd():
                c = self.__getChar()
                if c not in string.ascii_letters and c not in string.digits and c != '_':
                    break
                self.__head += 1
            return self.text[self.__tail:self.__head]
        else:
            return None

    def __getValue(self):
        self.__eatWhitespace()
        c = self.__getChar()
        if c == '"' or c == "'":
            single_quotes = (c == "'")
            self.__head += 1
            while not self.__isEnd():
                c = self.__getChar()
                if c == '\\':
                    self.__head += 1
                elif (c == '"' and not single_quotes) or (c == "'" and single_quotes):
                    self.__head += 1
                    break
                self.__head += 1
            if self.__isEnd():
                raise ParseError('closing quote expected in format string "{0}" for position {1}' \
                                    .format(self.text, self.__tail))
            return (self.__processEscapes(self.text[self.__tail + 1:self.__head - 1]),
                    "'" if single_quotes else '"')
        elif c.isalpha() or c in string.digits or c == '_':
            self.__head += 1
            while not self.__isEnd():
                c = self.__getChar()
                if not (c.isalpha() or c in string.digits or c == '_'):
                    break
                self.__head += 1
            return (self.text[self.__tail:self.__head], '')
        else:
            return None

    def __eatWhitespace(self):
        while True:
            c = self.__getChar()
            if c not in string.whitespace:
                break
            self.__head += 1
        self.__tail = self.__head

    def __getParam(self):
        name = self.__getIdent()
        if name is None:
            raise ParseError('identifier expected in format string "{0}" at position {1}' \
                             .format(self.text, self.__tail))
        self.__eatWhitespace()

        if self.__getChar() == '=':
            self.__head += 1
            self.__eatWhitespace()
            value = self.__getValue()
            if not value:
                raise ParseError('parameter value expected in format string "{0}" ' \
                                 + 'at position {1}'.format(self.text, self.__tail))
            return (name, value[0], value[1])
        else:
            return (name, None, None)

    def __getParams(self):
        params = {}
        while True:
            self.__eatWhitespace()
            name, value, quote_type = self.__getParam()
            if name in params:
                raise ParseError('duplicated parameter {0} in format string "{1}" at position {2}' \
                                 .format(name, self.text, self.__tail))
            params[name] = (value, quote_type)
            self.__eatWhitespace()
            if self.__getChar() != ',':
                break
            self.__head += 1
        return params

    _supported_escape_sequences = {
        '\\': '\\',
        't': '\t',
        'n': '\n',
        '\'': '\'',
        '"': '"',
        'a': '\a',
        'b': '\b',
        'f': '\f',
        'r': '\r',
        'v': '\v'
    }

    @staticmethod
    def __processEscapes(text):
        # I'm failed to make old variant work with non-ascii characters.
        # return str(bytes(text, 'utf-8').decode('unicode_escape'))
        result_text = ''
        tail, head = 0, 0
        escaping = False
        for char_index in range(len(text)):
            char = text[char_index]
            if escaping:
                if char in _FormatStringParser._supported_escape_sequences:
                    result_text += text[tail:head] + _FormatStringParser._supported_escape_sequences[char]
                    tail = head = char_index + 1
                else:
                    logger.debug('unknown escape sequence \\{0}, skipping'.format(char))
                escaping = False
            elif char == '\\':
                escaping = True
            else:
                head += 1

        if escaping:
            logger.debug('bad escape sequence at end of string')
            result_text += text[tail:-1]
        elif head != tail:
            result_text += text[tail:head]
        return result_text


class FormatString:
    """FormatString allows generating string that depends on properties of object
    basing on template string with special syntax.
    Template is a string with embedded blocks. Block has following syntax:
        {block_name: param_name = param_value, param2_name = param2_value}
    So each block has a name and list of parameters - name-value pairs. During
    generating such a block is replaced with value of tag linked to object
    and having same name as block. Parameters are used to set format options.

    If object has more than one tag with specified name, values will be formatted in
    special way according to values of max, separator, end and sort parameters.

    If tag value type is:
        TEXT: stored text is used
        NUMBER: number is converted to string
        LOCATOR: locator url is used
        OBJECT_REFERENCE: referenced object' display name is used
        NONE: empty string or value of 'none' parameter is used.

    Predefined parameters:
        default
            Specify value to use when no corresponding tag found. Default value is
            not used for NONE type tags (see none instead). Default value is ''

        none
            Specify value to use when tag value type is None. Default value is ''

        max
            When multiple tags found, determines maximal number of tags to be used
            for joining. Default value is 7. If value is 0, list will not be limited.

        separator
            When multiple tags found, determine separator to use between different
            tags' values. Default is ', '

        end
            When multiple tags found, determine text that will be displayed at three
            end of generated text when found tags count is greater than 'max' value.
            Default is ' ...'

        sort
            When multiple tags found, determine order in which values will be shown.
            Allowed values are 'asc' or 'desc' for ascending and descending sorting.
            Default is 'asc'

        locator
            When tag value type is LOCATOR, extracts only some parts of url. Allowed
            values are:
                url
                scheme
                path
                name - file or directory name
                basename - for files, this is file name without path and extension
                ext (or extension)
            Default value is 'url'

    Additional special block names can be registered. Special block names are
    started with '@'. Note that not all parameters may work correctly with special
    blocks.
    Predefined special blocks:

        @
        @name
            Replaced with object display name. No parameters supported. Avoid
            using this block in object display name templates as it can lead to
            infinite recursion.

    """

    custom_blocks = {
        '@': (lambda obj, token: [obj.displayNameTemplate]),
        '@name': (lambda obj, token: [obj.displayNameTemplate])
    }

    __known_params = ['default', 'none', 'max', 'sort', 'separator',
                      'end', 'locator']

    def __init__(self, template=''):
        if isinstance(template, FormatString):
            self.__template = template.template
        else:
            self.__template = template
        self.__tokens = []
        self.__parsed = False

    @property
    def template(self):
        return self.__template

    @template.setter
    def template(self, value):
        if self.__template != value:
            self.__template = value
            self.__parsed = False

    @property
    def tokens(self):
        self.__parse()
        return self.__tokens

    def __parse(self):
        if not self.__parsed:
            parser = _FormatStringParser()
            parser.parse(self.__template)
            self.__tokens = parser.tokens
            self.__parsed = True

    @staticmethod
    def registerCustomBlock(block_name, callback):
        if not block_name or block_name[0] != '@':
            raise TypeError('invalid block name {0}, should start with @'.format(block_name))
        if block_name in FormatString.custom_blocks:
            raise TypeError('custom block with same name already registered')
        FormatString.custom_blocks[block_name] = callback

    @staticmethod
    def unregisterCustomBlock(block_name):
        if block_name in FormatString.custom_blocks:
            del FormatString.custom_blocks[block_name]

    def __tagValue(self, tag_value, block):
        from organica.lib.objects import TagValue

        if tag_value.valueType == TagValue.TYPE_TEXT:
            return tag_value.text
        elif tag_value.valueType == TagValue.TYPE_NUMBER:
            return str(tag_value.number)
        elif tag_value.valueType == TagValue.TYPE_LOCATOR:
            url = tag_value.locator.url
            mode = block.getParam('locator', 'url')
            mode = mode.lower()
            if mode == 'url':
                return url.toString()
            elif mode == 'scheme':
                return url.scheme()
            elif mode == 'path':
                return url.toLocalFile if url.isLocalFile() else url.path()
            elif mode == 'name':
                # get not fileName(), but last component of path.
                path = url.toLocalFile()
                if path.endswith('/') or path.endswith('\\'):
                    path = path[:-1]
                return QFileInfo(path).fileName()
            elif mode == 'basename':
                return QFileInfo(url.toLocalFile()).baseName()
            elif mode == 'ext' or mode == 'extension':
                return QFileInfo(url.toLocalFile()).suffix()
            else:
                raise ParseError('unknown value for "locator" parameter: {0}'.format(mode))
        elif tag_value.valueType == TagValue.TYPE_NODE_REFERENCE:
            obj_identity = tag_value.nodeReference
            if obj_identity.isFlushed:
                return obj_identity.lib.object(obj_identity).displayNameTemplate
            else:
                return ''
        elif tag_value.valueType == TagValue.TYPE_NONE:
            return block.params.get('none', '')
        else:
            return ''

    def format(self, obj):
        from organica.lib.filters import TagQuery

        self.__parse()

        formatted = ''
        for token in self.__tokens:
            if not token.isBlock:
                formatted = formatted + token.value
            else:
                # find tag with this name first
                values = None
                if token.value.startswith('@'):
                    if token.value not in self.custom_blocks:
                        raise ParseError('unknown special block: {0}'.format(token.value))
                    values = self.custom_blocks[token.value](obj, token)
                else:
                    tags = obj.tags(TagQuery(tag_class=token.value))
                    if tags:
                        values = [self.__tagValue(t.value, token) for t in tags]

                    # find unknown parameters for standard blocks
                    for param in token.params.keys():
                        if param not in FormatString.__known_params:
                            logger.warn('unknown parameter: {0} in "{1}"'.format(param, self.template))

                if not values:
                    values = [token.getParam('default', '')]

                sort = token.getParam('sort', 'asc')
                if sort.lower() in ('asc', 'desc'):
                    values = sorted(values, key=str.lower, reverse=(sort.lower() == 'desc'))
                else:
                    raise ParseError('only allowed values for "sort" parameter are "asc" and "desc"')

                if len(values) == 1:
                    formatted += str(values[0])
                else:
                    overcount = False
                    try:
                        max_items = int(token.getParam('max', 7))
                    except ValueError:
                        raise ParseError('number excepted for "max" parameter value')

                    if 0 < max_items < len(values):
                        values = values[:max_items]
                        overcount = True

                    end = str(token.getParam('end', '...'))
                    separator = str(token.getParam('separator', ', '))

                    formatted += separator.join(values)
                    if overcount:
                        formatted += end

        return formatted

    @staticmethod
    def buildFromTokens(token_list):
        return _FormatStringParser.buildFromTokens(token_list)

    def __len__(self):
        return len(self.__template)
