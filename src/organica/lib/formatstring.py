import string
import organica.utils.helpers as helpers

class ParseError(Exception):
    pass

class FormatStringToken:
    def __init__(self):
        self.isBlock = False
        self.value = ''
        self.specs = {} # each spec is a tuple of two values: spec value
                        # and quote used for string.

class FormatStringParser:
    """
    Some object {tag_name: max_items = '', ellipsis = ''}

    block = block_name [: spec_list]
    block_name = (alpha|"_"|"@") {alpha|digit|"_"}
    ident = (alpha|"_") {alpha|digit|"_"}
    spec_list = spec {, spec}
    spec = ident ["=" value]
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
                self.__ctoken.value = self.__getIdent(is_block_name = True)
                if not self.__ctoken.value:
                    raise ParseError('block name expected in format string "{0}" at position {1}'.format(self.text, self.__head))
                self.__eatWhitespace()
                if self.__getChar() == ':':
                    self.__ctoken.specs = self.__getSpecs()
                    self.__eatWhitespace()
                if self.__getChar() != '}':
                    raise ParseError('end of block expected in format string "{0}" at position {1}'.format(self.text, self.__head))
            else:
                self.__ctoken.isBlock = False
                while not self.__isEnd() and self.__getChar() != '{':
                    if self.__getChar() == '\\':
                        self.__head += 1
                    self.__head += 1
                self.__ctoken.value = self.__processEscapes(self.text[self.__tail:self.__head])
            self.__tokens.append(self.__ctoken)
        self.__parsed = True

    @staticmethod
    def buildFromTokens(tokens):
        built = ''
        for token in tokens:
            if not token.isBlock:
                built.append(helpers.escape(token.value, '{\\'))
            else:
                built += '{' + token.name
                if token.specs:
                    built += ': '
                    need_comma = False
                    for spec_name, spec_value, quote_type in token.specs:
                        if not need_comma:
                            need_comma = True
                        else:
                            built += ', '

                        if spec_value is None:
                            built += spec_name
                        elif isinstance(spec_value, str):
                            built += '{0} = {2}{1}{2}'.format(spec_name,
                                                              helpers.escape(spec_value, '"\\'),
                                                              quote_type)
                        elif isinstance(spec_value, int):
                            built += '{0} = {1}'.format(spec_name, spec_value)
                        else:
                            raise TypeError('unexpected type for specificator value: {0}' \
                                            .format(type(spec_value)))
                built += '}'
        return built

    def __getChar(self):
        return self.text[self.__head] if self.__head < len(self.text) else '\0'

    def __isEnd(self):
        return len(self.text) >= self.__head

    def __getIdent(self, is_block_name = False):
        self.__eatWhitespace()
        c = self.__getChar()
        if c in string.ascii_letters or c == '_' or (is_block_name and c == '@'):
            self.__head += 1
            while not self.__isEnd():
                c = self.__getChar()
                self.__head += 1
                if c not in string.ascii_letters and c not in self.digits and c != '_':
                    break
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
                raise ParseError('closing quote expected in format string "{0}" for position {1}'.format(self.text, self.__tail))
            return (self.__processEscapes(self.text[self.__tail + 1:self.__head - 1]),
                    "'" if single_quotes else '"')
        elif c in string.ascii_letters or c in string.digits or c == '_':
            self.__head += 1
            while not self.__isEnd():
                c = self.__getChar()
                self.__head += 1
                if not (c in string.ascii_letters or c in string.digits or c == '_'):
                    break
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

    def __getSpec(self):
        name = self.__getIdent()
        if name is None:
            raise ParseError('identifier expected in format string "{0}" at position {1}'.format(self.text, self.__tail))
        self.__eatWhitespace()

        value = None
        quote_type = ''
        if self.__getChar() == '=':
            self.__head += 1
            self.__eatWhitespace()
            value = self.__getValue()
            if not value:
                raise ParseError('specificator value expected in format string "{0}" ' \
                                 + 'at position {1}'.format(self.text, self.__tail))
        return (name, value[0], value[1])

    def __getSpecList(self):
        specs = {}
        while True:
            self.__eatWhitespace()
            name, value, quote_type = self.__getSpec()
            if name in specs:
                raise ParseError('duplicated specificator {0} in format string "{1}" at position {2}' \
                                 .format(name, self.text, self.__tail))
            specs[name] = (value, quote_type)
            self.__eatWhitespace()
            if self.__getChar() != ',':
                break
        return specs

    @staticmethod
    def __processEscapes(text):
        return bytes(text, 'utf-8').decode('unicode_escape')

class FormatString:
    """
    FormatString allows generating string that depends on properties of object
    basing on template string with special syntax.
    Template is a string with embedded blocks. Block has following syntax:
        {block_name: spec_name = spec_value, spec2_name = spec2_value}
    So each block has a name and list of specificators - name-value pairs. During
    generating such a block is replaced with value of tag linked to object
    and having same name as block. Specificators are used to set format options.

    If object has more than one tag with specified name, values will be formatted in
    special way according to values of max_items, separator, end and sort specificators.

    If tag value type is:
        TEXT: stored text is used
        NUMBER: number is converted to string
        LOCATOR: locator url is used
        OBJECT_REFERENCE: referenced object' display name is used
        NONE: empty string or value of 'none' specificator is used.

    Predefined specificators:
        default
            Specify value to use when no corresponding tag found. Default value is
            not used for NONE type tags (see none instead). Default value is ''

        none
            Specify value to use when tag value type is None. Default value is ''

        max_items
            When multiple tags found, determines maximal number of tags to be used
            for joining. Default value is 7. If value is 0, list will not be limited.

        separator
            When multiple tags found, determine separator to use between different
            tags' values. Default is ', '

        end
            When multiple tags found, determine text that will be displayed at three
            end of generated text when found tags count is greater than max_items.
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
                file
                basename
                ext (or extension)
            Default value is 'url'

    Additional special block names can be registered. Special block names are
    started with '@'. Note that not all specificators may work correctly with special
    blocks.
    Predefined special blocks:

        @
        @name
            Replaced with object display name. No specificators supported. Avoid
            using this block in object display name templates as it can lead to
            infinite recursion.

    """

    custom_blocks = {
        '@': (lambda obj, token: obj.displayName),
        '@name': (lambda obj, token: obj.displayName)
    }

    def __init__(self, template = ''):
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
            parser = FormatStringParser()
            parser.parse(self.__template)
            self.__tokens = parser.tokens
            self.__parsed = True

    @staticmethod
    def registerCustomBlock(block_name, callback):
        if not block_name or block_name[0] != '@':
            raise ArgumentError('invalid block name {0}, should start with @'.format(block_name))
        if block_name in self.custom_blocks:
            raise ArgumentError('custom block with same name already registered')
        self.custom_blocks[block_name] = callback

    @staticmethod
    def unregisterCustomBlock(block_name):
        if block_name in self.custom_blocks:
            self.custom_blocks.remove(block_name)

    def __tagValue(self, tag_value, block):
        if tag_value.valueType == TagValue.TYPE_TEXT:
            return tag_value.text
        elif tag_value.valueType == TagValue.TYPE_NUMBER:
            return str(tag_value.number)
        elif tag_value.valueType == TagValue.TYPE_LOCATOR:
            url = tag_value.locator.url
            mode = block.specs['locator'] if 'locator' in block.specs else 'url'
            mode = mode.lower()
            if mode == 'url':
                return url.toString()
            elif mode == 'scheme':
                return url.scheme()
            elif mode == 'path':
                return url.toLocalFile if url.isLocalFile() else url.path()
            elif mode == 'file':
                return QFileInfo(url.toLocalFile()).fileName()
            elif mode == 'basename':
                return QFileInfo(url.toLocalFile()).baseName()
            elif mode == 'ext' or mode == 'extension':
                return QFileInfo(url.toLocalFile()).suffix()
            else:
                raise ParseError('unknown value for "locator" specificator: {0}'.format(mode))
        elif tag_value.valueType == TagValue.TYPE_OBJECT_REFERENCE:
            return tag_value.objectReference.displayName
        elif tag_value.valueType == TagValue.TYPE_NONE:
            return '' if 'none' not in block.specs else block.specs['none']
        else:
            return ''

    def format(self, obj):
        self.__parse()

        formatted = ''
        for token in self.__tokens:
            if not token.isBlock:
                formatted.append(token.value)
            else:
                # find tag with this name first
                values = None
                if token.value.startswith('@'):
                    if token.value not in self.custom_blocks:
                        raise ParseError('unknown special block: {0}'.format(token.value))
                    values = self.custom_blocks[token.value](obj, token)
                else:
                    tags = obj.tags(TagFilter().tagClass(token.value))
                    if tags:
                        values = [self.__tagValue(t.value) for t in tags]

                if not values:
                    if 'default' in token.specs and token.specs['default']:
                        values.append(token.specs['default'])
                    else:
                        values = ['']

                sort = token.specs.get('sort') or 'asc'
                if sort.lower() in ('asc', 'desc'):
                    values = sorted(values, key = str.lower, reverse = sort.lower() == 'asc')
                else:
                    raise ParseError('only allowed values for "sort" specificator are "asc" and "desc"')

                if len(values) == 1:
                    formatted.append(str(values))
                else:
                    overcount = False
                    max_items = token.specs['max_items'] or 7
                    if not isinstance(max_items, int):
                        raise ParseError('number expected for max_items specificator')

                    if max_items > 0 and len(values) > max_items:
                        values = values[:max_items]
                        overcount = True

                    end = str(token.specs.get('end') or '...')
                    separator = str(token.specs.get('separator') or ', ')

                    formatted.append(separator.join(values))
                    if overcount: formatted.append(end)

        return formatted
