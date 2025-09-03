from enum import Enum
from typing import Self, Any
from string import ascii_letters, digits


LETTERS: str = ascii_letters
LETTERS_DIGITS: str = ascii_letters + digits


class TT(Enum):
	EOF, LBR, RBR, COL, SEMICOL, IDENTIFIER, VALUE, CLASS, ID = range(9)

	def __str__(self):
		return super().__str__().replace("TT.", "")


class Position:
	def __init__(self, idx, ln, col, fn, ftxt):
		self.idx = idx
		self.ln = ln
		self.col = col
		self.fn = fn
		self.ftxt = ftxt

	def advance(self, current_char):
		self.idx += 1
		self.col += 1
		if current_char == "\n":
			self.col = 0
			self.ln += 1

	def copy(self):
		return Position(self.idx, self.ln, self.col, self.fn, self.ftxt)


class Token:
	def __init__(
		self, start_pos: Position, end_pos: Position, type: TT, value: str = ""
	):
		self.start_pos = start_pos
		self.end_pos = end_pos
		self.type = type
		self.value = value

	def __repr__(self):
		return f"{self.type}:'{self.value}'" if self.value else f"{self.type}"

	def __eq__(self, value):
		if not isinstance(value, Token):
			return False
		return self.type == value.type and self.value == value.value

	def __ne__(self, value):
		return not (self.__eq__(value))


class Error:
	def __init__(self, start_pos: Position, end_pos: Position, name: str, details: str):
		self.start_pos = start_pos
		self.end_pos = end_pos
		self.name = name
		self.details = details

	def __repr__(self):
		return f"File {self.start_pos.fn} (line {self.start_pos.ln + 1} column {self.start_pos.col + 1})\n\n{self.name}: {self.details}"


class ExpectedCharacter(Error):
	def __init__(self, start_pos: Position, end_pos: Position, details: str):
		super().__init__(start_pos, end_pos, "ExpectedCharacter", details)


class UnexpectedCharacter(Error):
	def __init__(self, start_pos: Position, end_pos: Position, details: str):
		super().__init__(start_pos, end_pos, "UnexpectedCharacter", details)


class InvalidSyntax(Error):
	def __init__(self, start_pos: Position, end_pos: Position, details: str):
		super().__init__(start_pos, end_pos, "InvalidSyntax", details)


class Result:
	def __init__(self):
		self.value = None
		self.error: Error | None = None

	def register(self, res: Self):
		if res.error:
			self.error = res.error
		return res.value

	def success(self, value):
		self.value = value
		return self

	def fail(self, error: Error):
		self.error = error
		return self


class Lexer:
	def __init__(self, fn: str, ftxt: str):
		self.fn = fn
		self.ftxt = ftxt

		self.pos = Position(-1, 0, -1, fn, ftxt)
		self.current_char: str | None = None
		self.advance()

	def advance(self):
		self.pos.advance(self.current_char)
		self.current_char = (
			self.ftxt[self.pos.idx] if self.pos.idx < len(self.ftxt) else None
		)

	def skip_whitespace(self):
		while self.current_char is not None and self.current_char in " \t\n":
			self.advance()

	def lex_special(self, token_type: TT, start_pos: Position):
		name: str = ""
		while (
			self.current_char is not None and self.current_char in LETTERS_DIGITS + "_-"
		):
			name += self.current_char
			self.advance()
		return Token(start_pos, self.pos.copy(), token_type, name)

	def lex(self):
		tokens: list[Token] = []
		res = Result()

		while self.current_char is not None:
			start_pos: Position = self.pos.copy()

			if self.current_char in " \t\n":
				self.skip_whitespace()

			elif self.current_char == "#":
				self.advance()
				tokens.append(self.lex_special(TT.ID, start_pos))

			elif self.current_char == ".":
				self.advance()
				tokens.append(self.lex_special(TT.CLASS, start_pos))

			elif self.current_char == "{":
				tokens.append(Token(start_pos, self.pos.copy(), TT.LBR))
				self.advance()

			elif self.current_char == "}":
				tokens.append(Token(start_pos, self.pos.copy(), TT.RBR))
				self.advance()

			elif self.current_char == ":":
				tokens.append(Token(start_pos, self.pos.copy(), TT.COL))
				self.advance()

			elif self.current_char == ";":
				tokens.append(Token(start_pos, self.pos.copy(), TT.SEMICOL))
				self.advance()

			elif self.current_char in LETTERS_DIGITS:
				tokens.append(self.lex_special(TT.IDENTIFIER, start_pos))

			else:
				return res.fail(
					UnexpectedCharacter(
						self.pos.copy(), self.pos.copy(), f"'{self.current_char}'"
					)
				)

		tokens.append(Token(self.pos.copy(), self.pos.copy(), TT.EOF))
		return res.success(tokens)


class Parser:
	def __init__(self, tokens: list[Token]):
		self.tokens = tokens
		self.idx = 0
		self.current_tok = tokens[self.idx]

	def advance(self):
		self.idx += 1
		if self.idx < len(self.tokens):
			self.current_tok = self.tokens[self.idx]
		return self.current_tok

	def parse(self):
		res = Result()
		rules: dict = {}
		while self.current_tok.type != TT.EOF:
			selectors = res.register(self.parse_selectors())
			if res.error:
				return res
			declarations = res.register(self.parse_block())
			if res.error:
				return res
			rules[selectors] = declarations
		return res.success(rules)

	def parse_selectors(self):
		res = Result()
		selectors = []

		while self.current_tok.type in (TT.CLASS, TT.ID, TT.IDENTIFIER):
			prefix: str = (
				"."
				if self.current_tok.type == TT.CLASS
				else "#" if self.current_tok.type == TT.ID else ""
			)
			value: str = prefix + self.current_tok.value
			selectors.append(value)
			self.advance()

		if self.current_tok.type != TT.LBR:
			return res.fail(
				InvalidSyntax(
					self.current_tok.start_pos,
					self.current_tok.end_pos,
					"Expected '{' after selectors.",
				)
			)
		self.advance()

		if not selectors:
			return res.fail(
				InvalidSyntax(
					self.current_tok.start_pos,
					self.current_tok.end_pos,
					"Expected selectors (tags, IDs, or classes) before '{'."
				)
			)
		
		return res.success(" ".join(selectors))

	def parse_block(self):
		res = Result()
		declarations: dict[str, list[str]] = {}

		while self.current_tok.type not in (TT.RBR, TT.EOF):
			if self.current_tok.type != TT.IDENTIFIER:
				return res.fail(
					InvalidSyntax(
						self.current_tok.start_pos,
						self.current_tok.end_pos,
						"Expected a property."
					)
				)
			prop_key: str = self.current_tok.value
			self.advance()

			if self.current_tok.type != TT.COL:
				return res.fail(
					InvalidSyntax(
						self.current_tok.start_pos,
						self.current_tok.end_pos,
						"Expected ':' after property."
					)
				)
			self.advance()

			values: list[str] = []
			while self.current_tok.type == TT.IDENTIFIER:
				values.append(self.current_tok.value)
				self.advance()
			
			if not values:
				return res.fail(
					InvalidSyntax(
						self.current_tok.start_pos,
						self.current_tok.end_pos,
						"Expected values after ':'."
					)
				)
			
			if self.current_tok.type != TT.SEMICOL:
				return res.fail(
					InvalidSyntax(
						self.current_tok.start_pos,
						self.current_tok.end_pos,
						"Expected ';' after values."
					)
				)
			self.advance()

			declarations[prop_key] = values
		
		if self.current_tok.type != TT.RBR:
			return res.fail(InvalidSyntax(
				self.current_tok.start_pos,
				self.current_tok.end_pos,
				"Expected '}' after block."
			))
		self.advance()		
		return res.success(declarations)


def parse_stylesheet(fn: str, ftxt: str):
	lexer = Lexer(fn, ftxt)
	lex_result = lexer.lex()
	if lex_result.error:
		return lex_result

	parser = Parser(lex_result.value)
	rules = parser.parse()
	return rules


if __name__ == "__main__":

	with open("EmeraldOS/files/style.gms", "r") as file:
		ftxt: str = file.read()

		if ftxt.strip():
			result = parse_stylesheet("style.gms", ftxt)
			print("Result:")
			print(result.error or result.value)
