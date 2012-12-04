import string
import organica.utils.helpers as helpers

class ParseError(Exception):
    pass

class FormatStringToken:
    def __init__(self):
        self.isBlock = False
        self.value = ''
        self.specs = None

class FormatStringParser:
    """
    Some object {tag_name: max_items = '', ellipsis = ''}

    block = ident [: spec_list]
    ident = (alpha|"_") {alpha|digit|"_"}
    spec_list = spec {, spec}
    spec = ident "=" value
    value = string_value | num_value
    string_value = ("\"" {*} "\"") | * {*}
    num_value = digit {digit}

    """

    def __init__(self):
        self.__tokens = []
        self.__tail, self.__head = 0, 0
        self.text = ''

    def parse(self, text):
        self.text = text

        while True:
            if self.__isEnd():
                break

            self.__ctoken = FormatStringToken()
            self.__tail = self.__head
            if self.__getChar() == '{':
                self.__ctoken.isBlock = True
                self.__ctoken.value = self.__getIdent()
                if not self.__ctoken.value:
                    raise ParseError('block name expected in format string "{0}" at position {1}'.format(self.text, self.__head))
                self.__eatWhitespace()
                if self.__getChar() == ':':
                    self.__ctoken.specs = self.__getSpecList()
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
                    for spec_name, spec_value in token.specs:
                        if not need_comma:
                            need_comma = True
                        else:
                            built += ', '
                        if spec_value is None:
                            built += spec_name
                        else:
                            built += '{0} = "{1}"'.format(spec_name, helpers.escape(spec_value, '"\\'))
                built += '}'

    def __getChar(self):
        return self.text[self.__head] if self.__head < len(self.text) else '\0'

    def __isEnd(self):
        return len(self.text) >= self.__head

    def __getIdent(self):
        self.__eatWhitespace()
        c = self.__getChar()
        if c in string.ascii_letters or c == '_':
            self.__head += 1
            while not self.__isEnd():
                c = self.__getChar()
                self.__head += 1
                if c not in string.ascii_letters and c not in self.digits and c != '_':
                    break
            return self.text[self.__tail:self.__head]
        else:
            return None

    def __getString(self):
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
            return self.__processEscapes(self.text[self.__tail + 1:self.__head - 1])
        # elif c in string.ascii_letters or c in string.digits or c == '_':
        #     self.__head += 1
        #     while not self.__isEnd():
        #         c = self.__getChar()
        #         if not (c in string.ascii_letters or c in string.digits or c == '_'):
        #             break
        #     return self.text[self.__tail:self.__head]
        return None

    def __getNumber(self):
        self.__eatWhitespace()
        if c in string.digits:
            self.__head += 1
            while not self.__isEnd():
                c = self.__getChar()
                self.__head += 1
                if c not in string.digits:
                    break
            return int(self.text[self.__tail:self.__head])
        return None

    def __eatWhitespace(self):
        while True:
            c = self.__getChar()
            if c not in string.whitespace:
                break
            self.__head += 1
        self.__tail = self.__head

    def __getValue(self):
        return self.__getString() or self.__getNumber()

    def __getSpec(self):
        name = self.__getIdent()
        if name is None:
            raise ParseError('specificator name expected in format string "{0}" at position {1}'.format(self.text, self.__tail))
        self.__eatWhitespace()

        value = None
        if self.__getChar() == '=':
            self.__head += 1
            self.__eatWhitespace()
            value = self.__getValue()
        return (name, value)

    def __getSpecList(self):
        specs = {}
        while True:
            self.__eatWhitespace()
            name, value = self.__getSpec()
            if name in specs:
                raise ParseError('duplicated specificator {0} in format string "{1}" at position {2}' \
                                 .format(name, self.text, self.__tail))
            specs.append((name, value))
            self.__eatWhitespace()
            if self.__getChar() != ',':
                break
        return specs

    @staticmethod
    def __processEscapes(text):
        return bytes(text, 'utf-8').decode('unicode_escape')

class FormatString:
    # values for formatting context
    FCONTEXT_NOTHING_SPECIAL = 0
    FCONTEXT_OBJECT_DISPLAY_NAME = 1
    FCONTEXT_PATH_TEMPLATE = 2

    custom_blocks = {}

    def __init__(self, template = ''):
        self.__template = template
        self.__tokens = []
        self.__parsed = False

    @property
    def template(self):
        return self.__template

    @template.setter
    def setTemplate(self, value):
        if self.__template != value:
            self.__template = value
            self.__parsed = False

    @property
    def tokens(self):
        self.__parse()
        return self.__tokens

    def __parse(self, text):
        if not self.__parsed:
            parser = FormatStringParser()
            parser.parse(text)
            self.__tokens = parser.tokens

    @staticmethod
    def registerCustomBlock(block_name, callback):
        if block_name in self.custom_blocks:
            raise ArgumentError('custom block with same name already registered')
        self.custom_blocks[block_name] = callback

    @staticmethod
    def unregisterCustomBlock(block_name):
        if block_name in self.custom_blocks:
            self.custom_blocks.remove(block_name)

    def format(self, obj, context = self.FCONTEXT_NOTHING_SPECIAL):
        self.__parse()

        formatted = ''
        for token in self.__tokens:
            if not token.isBlock:
                formatted.append(token.value)
            else:
                # find tag with this name first
                values = None
                tags = obj.tags(TagFilter.name(token.value))
                if tags and len(tags) > 0:
                    values = [t.value for t in tags]
                else:
                    # is it special block?
                    if token.value in self.custom_blocks:
                        sblock = self.custom_blocks[token.value]
                        values = sblock(obj, token, context)

                if not values:
                    if 'default' in token.specs and token.specs['default']:
                        values = token.specs

                if not values:
                    raise ParseError('value for block with name {0} is not defined for format string "{1}"' \
                                     .format(token.value, self.__template))

                if len(values) == 1:
                    formatted.append(str(values))
                else:
                    overcount = False
                    if 'max_items' in token.specs:
                        max_items = int(token.specs['max_items'])
                        if not isinstance(max_items, int):
                            self.__raiseParseError('number expected for max_items specificator', token)

                        if len(values) > max_items:
                            values = values[:max_items]
                            overcount = True

                    ellipsis = '...'
                    if 'ellipsis' in token.specs:
                        ellipsis = str(token.specs['ellipsis'])

                    separator = ', '
                    if 'separator' in token.specs:
                        separator = str(token.specs['separator'])

                    formatted.append(separator.join(values))
                    if overcount: formatted.append(ellipsis)

