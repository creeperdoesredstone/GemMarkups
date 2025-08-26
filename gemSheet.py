from enum import Enum
from typing import Self, Any
from string import ascii_letters, digits


LETTERS: str = ascii_letters
LETTERS_DIGITS: str = ascii_letters + digits


class TT(Enum):
	EOF, LBR, RBR, PROPERTY, VALUE, CLASS, ID, TAG = range(8)

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

	def lex(self):
		tokens: list[Token] = []
		res = Result()

		while self.current_char is not None:
			start_pos: Position = self.pos.copy()

			if self.current_char in " \t\n":
				self.skip_whitespace()
			elif self.current_char == "#":
				tokens.append(Token(start_pos, self.pos.copy(), TT.ID))
				self.advance()
			elif self.current_char == ".":
				tokens.append(Token(start_pos, self.pos.copy(), TT.CLASS))
				self.advance()
			elif self.current_char == "{":
				tokens.append(Token(start_pos, self.pos.copy(), TT.LBR))
				self.advance()
			elif self.current_char == "}":
				tokens.append(Token(start_pos, self.pos.copy(), TT.RBR))
				self.advance()
			elif self.current_char in LETTERS:
				property_name: str = ""
				while (
					self.current_char is not None and self.current_char in LETTERS + "-"
				):
					property_name += self.current_char
					self.advance()
				property_end_pos: Position = self.pos.copy()

				self.skip_whitespace()
				if self.current_char == "{":
					tokens.append(
						Token(start_pos, property_end_pos, TT.TAG, property_name)
					)
				else:
					if self.current_char != ":":
						return res.fail(
							ExpectedCharacter(
								self.pos.copy(),
								self.pos.copy(),
								"':' (after property)",
							)
						)
					self.advance()
					self.skip_whitespace()

					values_start_pos: Position = self.pos.copy()
					values: str = ""
					while (
						self.current_char is not None and self.current_char not in ";\n"
					):
						values += self.current_char
						self.advance()
					values_end_pos: Position = self.pos.copy()

					if self.current_char != ";":
						return res.fail(
							ExpectedCharacter(
								self.pos.copy(), self.pos.copy(), "';' (after value)"
							)
						)
					self.advance()

					tokens.append(
						Token(start_pos, property_end_pos, TT.PROPERTY, property_name)
					)
					tokens.append(
						Token(values_start_pos, values_end_pos, TT.VALUE, values)
					)
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
			selector = res.register(self.parse_selector())
			if res.error:
				return res
			declarations = res.register(self.parse_block())
			if res.error:
				return res
			rules[selector] = declarations
		return res.success(rules)

	def parse_selector(self):
		res = Result()
		tok = self.current_tok

		if tok.type in (TT.TAG, TT.ID, TT.CLASS):
			if tok.type == TT.TAG:
				selector = tok.value
			else:
				selector = "." if tok.type == TT.CLASS else "#"
				self.advance()

				if self.current_tok.type != TT.TAG:
					return res.fail(InvalidSyntax(
						self.current_tok.start_pos, self.current_tok.end_pos,
						f"Expected an identifier after '{selector}'"
					))
				selector += self.current_tok.value
			self.advance()
			return res.success(selector)
		return res.fail(
			InvalidSyntax(
				tok.start_pos, tok.end_pos, "Expected selector (tag, id, or class)"
			)
		)

	def parse_block(self):
		res = Result()

		if self.current_tok.type != TT.LBR:
			return res.fail(
				InvalidSyntax(
					self.current_tok.start_pos, self.current_tok.end_pos, "Expected '{'"
				)
			)
		self.advance()

		declarations = {}
		while self.current_tok.type not in (TT.RBR, TT.EOF):
			if self.current_tok.type == TT.PROPERTY:
				prop = self.current_tok.value
				self.advance()
				if self.current_tok.type != TT.VALUE:
					return res.fail(
						InvalidSyntax(
							self.current_tok.start_pos,
							self.current_tok.end_pos,
							"Expected value after property",
						)
					)
				val = self.current_tok.value
				declarations[prop] = val
				self.advance()
			else:
				self.advance()

		if self.current_tok.type != TT.RBR:
			return res.fail(
				InvalidSyntax(
					self.current_tok.start_pos,
					self.current_tok.end_pos,
					"Expected '}' after block.",
				)
			)

		self.advance()  # skip RBR
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
