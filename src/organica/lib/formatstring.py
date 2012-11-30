import string

class ParseError(Exception):
    pass

class FormatStringToken:
    def __init__(self):
        self.isBlock = False
        self.value = ''
        self.specs = None

class FormatStringParser:
    def __init__(self, text):
        self.__tokens = []
        self.__tail, self.__head = 0, 0
        self.text = text

    def parse(self):
        while True:
            if self.__isEnd():
                break

            ctoken = FormatStringToken()
            self.__tail = self.__head
            if self.__getChar() == '{':
                # enter block
                ctoken.isBlock = True
                ctoken.value = self.__getIdent()
                if not ctoken.value:
                    raise ParseError('block name expected in format string "{0}"" at position {1}'.format(self.text, self.__head))
                self.__eatWhitespace()
                if self.__getChar() == ':':
                    ctoken.specs = self.__getSpecList()
                self.__eatWhitespace()
                if self.__getChar() != '}':
                    raise ParseError('end of block expected in format string {0} at position {1}'.format(self.text, self.__head))
            else:
                ctoken.isBlock = False
                while not self.__isEnd() and self.__getChar() != '{':
                    if self.__getChar() == '\\':
                        self.__head += 1
                    self.__head += 1
                ctoken.value = self.processEscapes(self.text[self.__tail:self.__head])
            self.__tokens.append(ctoken)

    def __getChar(self):
        return self.text[self.__head] if self.__head < len(self.text) else None

    def __isEnd(self):
        return len(self.text) >= self.__head

    def __getIdent(self):
        c = self.__getChar()
        if c in string.ascii_letters or c == '_':
            self.__tail = self.__head
            self.__head += 1
            while self.__head < len(self.text):
                c = self.__getChar()
                self.__head += 1
                if c not in string.ascii_letters and c not in self.digits and c != '_':
                    break
            return self.text[self.__tail:self.__head]
        return None

    def __getString(self):
        c = self.__getChar()
        if c == '"' or c == "'":
            single_quotes = (c == "'")
            while True:
                self.__head += 1
                c = self.__getChar()
                if c == '\\':
                    self.__head += 1
                elif (c == '"' and not single_quotes) or (c == "'" and single_quotes):
                    self.__head += 1
            return self.text[self.__tail + 1:self.__head - 1]
        return None

    def __getNumber(self):
        if c in string.digits:
            self.__tail = self.__head
            while self.__head < len(self.text):
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
        if name is not None:
            value = None
            self.__eatWhitespace()
            if self.__getChar() == '=':
                self.__head += 1
                self.__eatWhitespace()
                value = self.__getValue()
            return (name, value)
        return None

    def __getSpecList(self):
        specs = {}
        while True:
            self.__eatWhitespace()
            name_value = self.__getSpec()
            if not name_value:
                raise ParseError('spec expected')
            name, value = *name_value
            if name in specs:
                raise ParseError('duplicated specificator {0} in format string {1}'.format(name, self.text))
            specs.append((name, value))
            self.__eatWhitespace()
            if self.__getChar() != ',':
                break
        return specs

    @staticmethod
    def processEscapes(text):
        return bytes(text, 'utf-8').decode('unicode_escape')

class FormatString:
    """
    Some object {tag_name: max_items = '', ellipsis = '', }

    block = ident [: spec_list]
    ident = (alpha|"_") {alpha|digit|"_"}
    spec_list = spec {, spec}
    spec = ident "=" value
    value = string_value | num_value
    string_value = ("\"" {*} "\"") | * {*}
    num_value = digit {digit}

    """

    # values for formatting context
    FCONTEXT_NOTHING_SPECIAL = 0
    FCONTEXT_OBJECT_DISPLAY_NAME = 1
    FCONTEXT_PATH_TEMPLATE = 2

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
        self.__tokens = []

        if text is None:
            return

        text_len = len(text)
        head, tail = 0, 0
        while True:
            ctoken = FormatStringToken()
            tail = head
            if head >= text_len:
                break
            elif text[head] == '{':
                # enter block
                pass
            else:
                ctoken.isBlock = False
                head += 1
                while head < text_len:
                    if text[head] == '\\':
                        head += 1
                    elif text[head] == '{':
                        break
                    head += 1
                ctoken.value = text[tail:head]

    @staticmethod
    def __getIdent(text, tail, head):
        c = text[head]
        if c in string.ascii_letters or c == '_':
            head += 1
            while head < len(text) and
