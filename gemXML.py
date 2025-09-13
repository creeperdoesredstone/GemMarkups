from enum import Enum
from typing import Self, Any
from string import ascii_letters, digits
from os.path import exists
from gemSheet import parse_stylesheet


LETTERS: str = ascii_letters
LETTERS_DIGITS: str = ascii_letters + digits

VALID_TAGS = [
	"window",
	"text",
	"rect",
	"circle",
	"line",
	"include",
	"div",
	"h1",
	"h2",
	"h3",
	"b",
	"i",
	"bi",
	"u",
]
VALID_INCLUDES = ["style", "md"]

CLASSES: dict[str, list] = {}
IDS: dict[str, Any] = {}


class TT(Enum):
	EOF, TAG, CLOSE, TEXT, DATA, ATTRIBUTE = range(6)

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


class UnknownTag(Error):
	def __init__(self, start_pos, end_pos, details):
		super().__init__(start_pos, end_pos, "UnknownTag", details)


class MissingAttribute(Error):
	def __init__(self, start_pos, end_pos, details):
		super().__init__(start_pos, end_pos, "MissingAttribute", details)


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

		asterisk_mds: list[str] = ["i", "b", "bi"]

		while self.current_char is not None:
			start_pos: Position = self.pos.copy()
			attributes: dict[str, str] = {}

			if self.current_char in " \t\n":
				self.advance()

			elif self.current_char == "<":
				self.advance()
				self.skip_whitespace()
				is_closing_tag = False
				tag_name: str = ""

				if self.current_char == "/":
					is_closing_tag = True
					self.advance()

				if self.current_char not in LETTERS:
					return res.fail(
						ExpectedCharacter(
							self.pos.copy(),
							self.pos.copy(),
							"Expected a letter after '"
							+ ("</" if is_closing_tag else "<")
							+ "'",
						)
					)
				tag_name += self.current_char
				self.advance()

				while (
					self.current_char is not None
					and self.current_char in LETTERS_DIGITS
				):
					tag_name += self.current_char
					self.advance()

				# Check tag name
				if tag_name not in VALID_TAGS:
					return res.fail(UnknownTag(start_pos, self.pos.copy(), tag_name))

				if self.current_char != ">":  # Attributes
					if self.current_char not in " \t\n":
						return res.fail(
							ExpectedCharacter(
								self.pos.copy(),
								self.pos.copy(),
								"Expected '>' or a whitespace after tag name.",
							)
						)

					# maps attribute to values
					self.skip_whitespace()

					while self.current_char is not None and self.current_char != ">":
						attribute: str = ""
						data: str = ""
						while (
							self.current_char is not None
							and self.current_char in LETTERS
						):
							attribute += self.current_char
							self.advance()

						self.skip_whitespace()
						if self.current_char != "=":
							return res.fail(
								ExpectedCharacter(
									self.pos.copy(),
									self.pos.copy(),
									f"Expected '=' after attribute, found '{self.current_char}' instead.",
								)
							)
						self.advance()
						self.skip_whitespace()

						if self.current_char != '"':
							return res.fail(
								ExpectedCharacter(
									self.pos.copy(),
									self.pos.copy(),
									"Expected '\"' after '='.",
								)
							)
						self.advance()
						while (
							self.current_char is not None
							and self.current_char not in '"\n'
						):
							data += self.current_char
							self.advance()

						if self.current_char != '"':
							return res.fail(
								ExpectedCharacter(
									self.pos.copy(),
									self.pos.copy(),
									"Expected terminating '\"' character.",
								)
							)

						attributes[attribute] = data
						self.advance()
						self.skip_whitespace()

				tokens.append(
					Token(
						start_pos,
						self.pos.copy(),
						TT.CLOSE if is_closing_tag else TT.TAG,
						tag_name,
					)
				)
				for attr in attributes.keys():
					tokens.append(Token(None, None, TT.ATTRIBUTE, attr))
					tokens.append(Token(None, None, TT.DATA, attributes[attr]))

				self.advance()

			elif self.current_char == '"':
				self.advance()
				data: str = ""
				while self.current_char is not None and self.current_char not in '"\n':
					data += self.current_char
					self.advance()

				if self.current_char != '"':
					return res.fail(
						ExpectedCharacter(
							self.pos.copy(),
							self.pos.copy(),
							"Expected terminating '\"' character.",
						)
					)
				tokens.append(Token(start_pos, self.pos.copy(), TT.DATA, data))
				self.advance()

			elif self.current_char == "#":
				count: int = 0
				while self.current_char == "#":
					count += 1
					self.advance()
				while self.current_char is not None and self.current_char in " \t":
					self.advance()

				if count > 3:
					return res.fail(
						InvalidSyntax(
							start_pos,
							self.pos.copy(),
							"Expected a max of 3 '#' characters.",
						)
					)

				content_start_pos: Position = self.pos.copy()
				content: str = ""

				while self.current_char is not None and self.current_char != "\n":
					content += self.current_char
					self.advance()

				if not content:
					return res.fail(
						InvalidSyntax(
							content_start_pos,
							self.pos.copy(),
							f"Expected content after '{'#' * count}'.",
						)
					)

				content_lexer = Lexer("<md-content>", content)
				content_tokens: list[Token] = res.register(content_lexer.lex())[:-1]
				if res.error:
					return res

				for tok in content_tokens:
					tok.start_pos = content_start_pos
					tok.end_pos = self.pos.copy()

				tokens.append(Token(start_pos, content_start_pos, TT.TAG, f"h{count}"))
				tokens.extend(content_tokens)
				tokens.append(
					Token(self.pos.copy(), self.pos.copy(), TT.CLOSE, f"h{count}")
				)

			elif self.current_char == "*":
				count = 0
				while self.current_char == "*":
					count += 1
					self.advance()
				while self.current_char is not None and self.current_char in " \t":
					self.advance()

				if count > 3:
					return res.fail(
						InvalidSyntax(
							start_pos,
							self.pos.copy(),
							"Expected a max of 3 '*' characters.",
						)
					)

				content_start_pos: Position = self.pos.copy()
				content: str = ""

				while self.current_char is not None and self.current_char not in "*\n":
					content += self.current_char
					self.advance()

				if not content:
					return res.fail(
						InvalidSyntax(
							content_start_pos,
							self.pos.copy(),
							f"Expected content after '{'*' * count}'.",
						)
					)

				if self.current_char in (None, "\n"):
					return res.fail(
						InvalidSyntax(
							self.pos.copy(),
							self.pos.copy(),
							"Reached EOL when parsing Markdown tag.",
						)
					)

				end_count: int = 0
				while self.current_char == "*":
					end_count += 1
					self.advance()

				if end_count != count:
					return res.fail(
						InvalidSyntax(
							self.pos.copy(),
							self.pos.copy(),
							f"Expected {count} '*' characters, got {end_count} '*' characters instead.",
						)
					)

				content_lexer = Lexer("<md-content>", content)
				content_tokens: list[Token] = res.register(content_lexer.lex())[:-1]
				if res.error:
					return res

				for tok in content_tokens:
					tok.start_pos = content_start_pos
					tok.end_pos = self.pos.copy()

				tokens.append(
					Token(start_pos, content_start_pos, TT.TAG, asterisk_mds[count - 1])
				)
				tokens.extend(content_tokens)
				tokens.append(
					Token(
						self.pos.copy(),
						self.pos.copy(),
						TT.CLOSE,
						asterisk_mds[count - 1],
					)
				)

			else:
				content: str = ""

				while (
					self.current_char is not None and self.current_char not in "\n<>\"'"
				):
					content += self.current_char
					self.advance()

				if content == "":
					return res.fail(
						UnexpectedCharacter(
							self.pos.copy(),
							self.pos.copy(),
							f"Unexpected Character: '{self.current_char}'",
						)
					)

				tokens.append(
					Token(
						start_pos,
						self.pos.copy(),
						TT.TEXT,
						content,
					)
				)

		tokens.append(Token(self.pos.copy(), self.pos.copy(), TT.EOF))
		return res.success(tokens)


class NodeList:
	def __init__(self, start_pos: Position, end_pos: Position, body: list):
		self.start_pos = start_pos
		self.end_pos = end_pos
		self.body = body

	def __repr__(self):
		return f"{self.body if len(self.body) != 1 else self.body[0]}"


class TextNode:
	def __init__(self, start_pos: Position, end_pos: Position, content: str):
		self.start_pos = start_pos
		self.end_pos = end_pos
		self.content = content

	def __repr__(self):
		return self.content


class TagNode:
	def __init__(
		self,
		start_pos: Position,
		end_pos: Position,
		attributes: dict[str, str],
		tag_name: str,
		content: Any,
	):
		self.start_pos = start_pos
		self.end_pos = end_pos
		self.attributes = attributes
		self.tag_name = tag_name
		self.content = content

	def __repr__(self):
		result: str = (
			f"<{self.tag_name} {self.attributes if self.attributes else ''}>\n"
		)
		content_str: str = f"{self.content}"
		for line in content_str.splitlines():
			result += "  " + line + "\n"
		result += f"</{self.tag_name}>"

		return result


class Parser:
	def __init__(self, tokens: list[Token]):
		self.tokens = tokens
		self.token_idx = -1
		self.current_tok = None

		self.advance()

	def advance(self):
		self.token_idx += 1
		if self.token_idx < len(self.tokens):
			self.current_tok = self.tokens[self.token_idx]

	def parse(self):
		res = Result()

		body = res.register(self.parse_tags())
		if res.error:
			return res

		if self.current_tok.type != TT.EOF:
			return res.fail(
				InvalidSyntax(
					self.current_tok.start_pos,
					self.current_tok.end_pos,
					"Cannot fully parse the file.",
				)
			)

		return res.success(body)

	def parse_tags(self):
		res = Result()
		body: list = []
		start_pos: Position = self.current_tok.start_pos
		end_pos: Position = self.current_tok.end_pos

		while self.current_tok.type not in (TT.CLOSE, TT.EOF):
			tag: TagNode | TextNode = res.register(self.parse_tag())
			if res.error:
				return res
			end_pos = tag.end_pos

			body.append(tag)

		return res.success(NodeList(start_pos, end_pos, body))

	def parse_tag(self):
		res = Result()

		if self.current_tok.type == TT.TEXT:
			return self.parse_text()

		if self.current_tok.type != TT.TAG:
			return res.fail(
				InvalidSyntax(
					self.current_tok.start_pos,
					self.current_tok.end_pos,
					f"Expected a tag, found token ({self.current_tok}) instead.",
				)
			)
		start_pos: Position = self.current_tok.start_pos
		tag_name: str = self.current_tok.value
		self.advance()

		attributes: dict[str, str] = {}

		while self.current_tok.type == TT.ATTRIBUTE:
			attribute = self.current_tok.value
			self.advance()
			data = self.current_tok.value
			self.advance()

			attributes[attribute] = data

		content = res.register(self.parse_tags())
		if res.error:
			return res

		if self.current_tok != Token(None, None, TT.CLOSE, tag_name):
			return res.fail(
				InvalidSyntax(
					self.current_tok.start_pos,
					self.current_tok.end_pos,
					f"Expected </{tag_name}>, found token {self.current_tok} instead.",
				)
			)
		end_pos: Position = self.current_tok.end_pos
		self.advance()

		return res.success(TagNode(start_pos, end_pos, attributes, tag_name, content))

	def parse_text(self):
		res = Result().success(
			TextNode(
				self.current_tok.start_pos,
				self.current_tok.end_pos,
				self.current_tok.value,
			)
		)
		self.advance()

		return res


class Window:
	def __init__(self, x: int, y: int, width: int, height: int, title: str):
		self.x = x
		self.y = y
		self.width = width
		self.height = height
		self.title = title

		self.contents: list[Any] = []
		self.styles: dict[str, Any] = {}

	def __str__(self):
		result: str = (
			f"Window {self.title}({self.x}, {self.y}, {self.width}, {self.height}) [\n"
		)
		for content in self.contents:
			result += f"    {content}\n".replace("(", "").replace(")", "")
		result += "]"

		return result


class Text:
	def __init__(self, contents: str):
		self.contents = contents
		self.styles: dict[str, Any] = {}

	def __repr__(self):
		return f"Text ('{self.contents}')"


class Header:
	def __init__(self, header_type: int, contents: list):
		self.header_type = header_type
		self.contents = contents

		self.styles: dict[str, Any] = {}

	def __repr__(self):
		return f"H{self.header_type} {self.contents}"


class StyledContent:
	def __init__(self, style: str, contents: list):
		self.style = style
		self.contents = contents

		self.styles: dict[str, Any] = {}

	def __repr__(self):
		return f"{self.style.upper()} {self.contents}"


class Rect:
	def __init__(self, x: int, y: int, width: int, height: int):
		self.x = x
		self.y = y
		self.width = width
		self.height = height

		self.contents = []
		self.styles: dict[str, Any] = {}

	def __repr__(self):
		return f"Rectangle ({self.x}, {self.y}, {self.width}, {self.height})"


class Circle:
	def __init__(self, x: int, y: int, radius: int):
		self.x = x
		self.y = y
		self.radius = radius

		self.contents = []
		self.styles: dict[str, Any] = {}

	def __repr__(self):
		return f"Circle ({self.x}, {self.y}, {self.radius})"


class Line:
	def __init__(self, start_x: int, start_y: int, end_x: int, end_y: int):
		self.start_x = start_x
		self.start_y = start_y
		self.end_x = end_x
		self.end_y = end_y

		self.contents = []
		self.styles: dict[str, Any] = {}

	def __repr__(self):
		return f"Line ({self.start_x}, {self.start_y}, {self.end_x}, {self.end_y})"


class Div:
	def __init__(self, contents: list):
		self.contents = contents
		self.styles: dict[str, Any] = {}

	def __repr__(self):
		return f"DIV {self.contents}"


class Compiler:
	def __init__(self):
		self.window = None
		CLASSES.clear()
		IDS.clear()

		self.styles: list[str] = []

	def validate(self, node_list: NodeList):
		res = Result()

		if len(node_list.body) != 1:
			return res.fail(
				Error(
					node_list.start_pos,
					node_list.end_pos,
					"WindowError",
					"A GemXML file can only support one window at a time.",
				)
			)

		if (
			not isinstance(node_list.body[0], TagNode)
			or node_list.body[0].tag_name != "window"
		):
			return res.fail(
				Error(
					node_list.start_pos,
					node_list.end_pos,
					"WindowError",
					"Expected <window> tag at the start of the file.",
				)
			)

		return res.success(True)

	def visit(self, node):
		method_name: str = f"visit{type(node).__name__}"
		method = getattr(self, method_name, self.no_visit_method)
		return method(node)

	def no_visit_method(self, node):
		return Result().fail(f"No visit{type(node).__name__} method defined.")

	def visitNodeList(self, node: NodeList):
		res = Result()
		registered = None
		results = []

		for stmt in node.body:
			registered = res.register(self.visit(stmt))
			if res.error:
				return res

			results.append(registered)

		return res.success(results)

	def visitTextNode(self, node: TextNode):
		return self.visitTagNode(
			TagNode(node.start_pos, node.end_pos, {}, "text", node.content)
		)

	def visitTagNode(self, node: TagNode):
		res = Result()

		def update_class_and_id(obj) -> None:
			if "class" in node.attributes:
				class_name: str = node.attributes["class"]
				if class_name in CLASSES:
					CLASSES[class_name].append(obj)
				else:
					CLASSES[class_name] = [obj]
			if "id" in node.attributes:
				id_name: str = node.attributes["id"]
				if id_name in IDS.values():
					return res.fail(
						f"ID {id_name} is already used by object {type(IDS[id_name]).__name__}."
					)
				else:
					IDS[obj] = id_name

		match node.tag_name:

			case "window":
				# read window attributes
				window_x: int = int(node.attributes.get("x", 45))
				window_y: int = int(node.attributes.get("y", 35))
				window_width: int = int(node.attributes.get("width", 30))
				window_height: int = int(node.attributes.get("height", 20))
				window_title: str = node.attributes.get("title", "Title")

				if self.window is not None:
					return res.fail(
						Error(
							node.start_pos,
							node.end_pos,
							"WindowError",
							"There can only be one.",
						)
					)

				self.window = Window(
					window_x, window_y, window_width, window_height, window_title
				)

				res.register(self.visit(node.content))
				if res.error:
					return res

				return res.success(self.window)

			case "text":
				text = Text(node.content)
				self.window.contents.append(text)
				update_class_and_id(text)

				return res.success(text)

			case "rect":
				# read rect attributes
				rect_x: int = int(node.attributes.get("x", self.window.width // 2 - 5))
				rect_y: int = int(node.attributes.get("y", self.window.height // 2 - 3))
				rect_width: int = int(node.attributes.get("width", 10))
				rect_height: int = int(node.attributes.get("height", 6))

				rect = Rect(rect_x, rect_y, rect_width, rect_height)
				self.window.contents.append(rect)
				update_class_and_id(rect)

				return res.success(rect)

			case "circle":
				# read rect attributes
				circle_x: int = int(node.attributes.get("x", self.window.width // 2))
				circle_y: int = int(node.attributes.get("y", self.window.height // 2))
				circle_radius: int = int(node.attributes.get("radius", 4))

				circle = Circle(circle_x, circle_y, circle_radius)
				self.window.contents.append(circle)
				update_class_and_id(circle)

				return res.success(circle)

			case "line":
				# read line attributes
				for attr in ("startx", "starty", "endx", "endy"):
					if attr not in node.attributes.keys():
						return res.fail(
							MissingAttribute(
								node.start_pos,
								node.end_pos,
								f"Missing attribute: '{attr}'",
							)
						)

				start_x: int = int(node.attributes["startx"])
				start_y: int = int(node.attributes["starty"])
				end_x: int = int(node.attributes["endx"])
				end_y: int = int(node.attributes["endy"])

				line = Line(start_x, start_y, end_x, end_y)
				self.window.contents.append(line)
				update_class_and_id(line)

				return res.success(line)

			case "div":
				start_pos: int = len(self.window.contents)

				content = res.register(self.visit(node.content))
				if res.error:
					return res

				self.window.contents = self.window.contents[:start_pos]

				div = Div(content)
				self.window.contents.append(div)
				update_class_and_id(div)

				return res.success(div)

			case "include":
				if "as" not in node.attributes:
					return res.fail(
						MissingAttribute(
							node.start_pos,
							node.end_pos,
							f"Missing attribute: 'as'",
						)
					)
				if node.attributes["as"] not in VALID_INCLUDES:
					return res.fail(
						Error(
							node.start_pos,
							node.end_pos,
							"AttributeError",
							f"Expected one of the following for 'as' attribute: {", ".join(VALID_INCLUDES)}.",
						)
					)

				if not node.content:
					return res.fail(
						MissingAttribute(
							node.start_pos, node.end_pos, "File path cannot be empty."
						)
					)

				if not exists(f"EmeraldOS/files/{node.content.body[0].content}"):
					return res.fail(
						Error(
							node.start_pos,
							node.end_pos,
							"FileError",
							f"Cannot find file {node.content}.",
						)
					)

				def check_extension(file_ext: str, file_type: str) -> Result:
					local_res = Result()
					if not node.content.body[0].content.endswith(file_ext):
						return local_res.fail(
							Error(
								node.start_pos,
								node.end_pos,
								"FileError",
								f"{file_type} must end in '{file_ext}'.",
							)
						)
					return local_res.success(None)

				match node.attributes["as"]:
					case "style":
						res.register(check_extension(".gms", "Stylesheet"))
						self.styles.append(node.content)
					case "md":
						res.register(check_extension(".md", "Markdown file"))

				if res.error:
					return res

				return res.success(None)

			case _:
				if node.tag_name in ("h1", "h2", "h3"):
					start_pos: int = len(self.window.contents)

					content = res.register(self.visit(node.content))
					if res.error:
						return res

					self.window.contents = self.window.contents[:start_pos]

					header = Header(int(node.tag_name[1]), content)
					self.window.contents.append(header)
					update_class_and_id(header)

					return res.success(header)

				if node.tag_name in ("b", "i", "bi", "u"):
					start_pos: int = len(self.window.contents)

					content = res.register(self.visit(node.content))
					if res.error:
						return res

					self.window.contents = self.window.contents[:start_pos]

					styled_content = StyledContent(node.tag_name, content)
					self.window.contents.append(styled_content)
					update_class_and_id(styled_content)

					return res.success(styled_content)

				return res.fail(
					UnknownTag(
						node.start_pos,
						node.end_pos,
						f"<{node.tag_name}> (when compiling)",
					)
				)


def apply_cascading_styles(
	styles: dict[str, dict[str, list]], node: Any, parent: Any = None
):
	if parent:
		for prop, value in parent.styles.items():
			node.styles[prop] = value

	tag_name: str = type(node).__name__.lower()
	node_id = IDS.get(node, None)
	node_classes = [
		class_name for class_name, nodes in CLASSES.items() if node in nodes
	]

	for selectors, style in styles.items():
		selected: bool = False

		splitted_selectors: list[str] = selectors.split(" ")

		if tag_name in splitted_selectors:
			selected = True
		if node_id and "#" + node_id in splitted_selectors:
			selected = True
		for class_name in node_classes:
			if "." + class_name in splitted_selectors:
				selected = True

		if selected:
			for prop_key, value in style.items():
				node.styles[prop_key] = value

	if hasattr(node, "contents") and isinstance(node.contents, list):
		for child in node.contents:
			apply_cascading_styles(styles, child, node)


def process(fn: str, ftxt: str):
	lexer = Lexer(fn, ftxt)
	lex_result: Result = lexer.lex()
	if lex_result.error:
		return lex_result

	parser = Parser(lex_result.value)
	ast = parser.parse()
	if ast.error:
		return ast

	compiler = Compiler()
	validate = compiler.validate(ast.value)
	if validate.error:
		return validate

	result = compiler.visit(ast.value)
	if result.error:
		return result

	for style in compiler.styles:
		with open(f"EmeraldOS/files/{style}", "r") as file:
			style_result = parse_stylesheet(style, file.read())
			if style_result.error:
				return style_result

			apply_cascading_styles(style_result.value, compiler.window)

	# result.value = result.value[0]
	return result


if __name__ == "__main__":

	with open("EmeraldOS/files/data.xml", "r") as file:
		ftxt: str = file.read()

		if ftxt.strip():
			result = process("data.xml", ftxt)
			print("Result:")
			print(result.error or result.value[0])
			print(f"\nClasses:\n{CLASSES}")
			print(f"\nIDs:\n{IDS}")

			if not result.error:
				print("\nStyles:")
				print("Window's style:", result.value[0].styles)  # window
				print(
					"#lighter id style:", result.value[0].contents[1].contents[1].styles
				)  # text with 'lighter' id
