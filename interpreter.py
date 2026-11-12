#!/usr/bin/env python3

import re
import sys

class Token:
    def __init__(self, type, value, line=0):
        self.type = type
        self.value = value
        self.line = line

class Lexer:
    def __init__(self, text):
        self.text = text
        self.pos = 0
        self.line = 1
        
    def tokenize(self):
        tokens = []
        while self.pos < len(self.text):
            if self.text[self.pos].isspace():
                if self.text[self.pos] == '\n':
                    self.line += 1
                self.pos += 1
                continue
                
            # Numbers
            if self.text[self.pos].isdigit():
                num = ''
                while self.pos < len(self.text) and (self.text[self.pos].isdigit() or self.text[self.pos] == '.'):
                    num += self.text[self.pos]
                    self.pos += 1
                tokens.append(Token('NUMBER', float(num) if '.' in num else int(num), self.line))
                continue
                
            # Identifiers and keywords
            if self.text[self.pos].isalpha() or self.text[self.pos] == '_':
                word = ''
                while self.pos < len(self.text) and (self.text[self.pos].isalnum() or self.text[self.pos] == '_'):
                    word += self.text[self.pos]
                    self.pos += 1
                    
                keywords = {'function': 'FUNCTION', 'return': 'RETURN', 'print': 'PRINT', 
                           'if': 'IF', 'else': 'ELSE', 'while': 'WHILE'}
                token_type = keywords.get(word, 'IDENTIFIER')
                tokens.append(Token(token_type, word, self.line))
                continue
                
            # Strings
            if self.text[self.pos] == '"':
                self.pos += 1
                string = ''
                while self.pos < len(self.text) and self.text[self.pos] != '"':
                    if self.text[self.pos] == '\\' and self.pos + 1 < len(self.text):
                        next_char = self.text[self.pos + 1]
                        if next_char == 'n':
                            string += '\n'
                            self.pos += 2
                        elif next_char == 't':
                            string += '\t'
                            self.pos += 2
                        elif next_char == '\\':
                            string += '\\'
                            self.pos += 2
                        elif next_char == '"':
                            string += '"'
                            self.pos += 2
                        else:
                            string += self.text[self.pos]
                            self.pos += 1
                    else:
                        string += self.text[self.pos]
                        self.pos += 1
                self.pos += 1  # Skip closing quote
                tokens.append(Token('STRING', string, self.line))
                continue
                
            # Two-character operators
            if self.pos + 1 < len(self.text):
                two_char = self.text[self.pos:self.pos+2]
                if two_char in ['==', '!=', '<=', '>=', '&&', '||']:
                    tokens.append(Token(two_char, two_char, self.line))
                    self.pos += 2
                    continue
                    
            # Single-character tokens
            char = self.text[self.pos]
            if char in '+-*/%=<>(){}[];,[]':
                tokens.append(Token(char, char, self.line))
            self.pos += 1
            
        return tokens

class ASTNode:
    pass

class Program(ASTNode):
    def __init__(self, statements):
        self.statements = statements

class FunctionDef(ASTNode):
    def __init__(self, name, params, body):
        self.name = name
        self.params = params
        self.body = body

class Return(ASTNode):
    def __init__(self, expr):
        self.expr = expr

class Print(ASTNode):
    def __init__(self, expr):
        self.expr = expr

class If(ASTNode):
    def __init__(self, condition, then_block, else_block=None):
        self.condition = condition
        self.then_block = then_block
        self.else_block = else_block

class While(ASTNode):
    def __init__(self, condition, body):
        self.condition = condition
        self.body = body

class Assignment(ASTNode):
    def __init__(self, name, expr):
        self.name = name
        self.expr = expr

class BinaryOp(ASTNode):
    def __init__(self, left, op, right):
        self.left = left
        self.op = op
        self.right = right

class FunctionCall(ASTNode):
    def __init__(self, name, args):
        self.name = name
        self.args = args

class Variable(ASTNode):
    def __init__(self, name):
        self.name = name

class Number(ASTNode):
    def __init__(self, value):
        self.value = value

class String(ASTNode):
    def __init__(self, value):
        self.value = value

class ArrayAccess(ASTNode):
    def __init__(self, array_name, index):
        self.array_name = array_name
        self.index = index

class ArrayAssignment(ASTNode):
    def __init__(self, array_name, index, value):
        self.array_name = array_name
        self.index = index
        self.value = value

class ArrayLiteral(ASTNode):
    def __init__(self, elements):
        self.elements = elements

class HashMap(ASTNode):
    def __init__(self):
        pass

class IndexAccess(ASTNode):
    def __init__(self, obj, index):
        self.obj = obj
        self.index = index

class IndexAssignment(ASTNode):
    def __init__(self, obj, index, value):
        self.obj = obj
        self.index = index
        self.value = value

class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0
        
    def current_token(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None
        
    def consume(self, expected_type=None):
        token = self.current_token()
        if expected_type and token.type != expected_type:
            raise SyntaxError(f"Expected {expected_type}, got {token.type}")
        self.pos += 1
        return token
        
    def parse(self):
        statements = []
        while self.pos < len(self.tokens):
            stmt = self.parse_statement()
            if stmt:
                statements.append(stmt)
        return Program(statements)
        
    def parse_statement(self):
        token = self.current_token()
        if not token:
            return None
            
        if token.type == 'FUNCTION':
            return self.parse_function()
        elif token.type == 'RETURN':
            return self.parse_return()
        elif token.type == 'PRINT':
            return self.parse_print()
        elif token.type == 'IF':
            return self.parse_if()
        elif token.type == 'WHILE':
            return self.parse_while()
        elif token.type == 'IDENTIFIER':
            # Check if it's a function call or assignment
            if self.pos + 1 < len(self.tokens) and self.tokens[self.pos + 1].type == '(':
                # Function call statement
                expr = self.parse_expression()
                self.consume(';')
                return expr
            else:
                return self.parse_assignment()
        else:
            raise SyntaxError(f"Unexpected token: {token.type}")
            
    def parse_function(self):
        self.consume('FUNCTION')
        name = self.consume('IDENTIFIER').value
        self.consume('(')
        
        params = []
        if self.current_token().type != ')':
            params.append(self.consume('IDENTIFIER').value)
            while self.current_token().type == ',':
                self.consume(',')
                params.append(self.consume('IDENTIFIER').value)
        
        self.consume(')')
        self.consume('{')
        
        body = []
        while self.current_token().type != '}':
            body.append(self.parse_statement())
            
        self.consume('}')
        return FunctionDef(name, params, body)
        
    def parse_return(self):
        self.consume('RETURN')
        expr = self.parse_expression()
        self.consume(';')
        return Return(expr)
        
    def parse_print(self):
        self.consume('PRINT')
        self.consume('(')
        expr = self.parse_expression()
        self.consume(')')
        self.consume(';')
        return Print(expr)
        
    def parse_if(self):
        self.consume('IF')
        self.consume('(')
        condition = self.parse_expression()
        self.consume(')')
        self.consume('{')
        
        then_block = []
        while self.current_token().type != '}':
            then_block.append(self.parse_statement())
        self.consume('}')
        
        else_block = None
        if self.current_token() and self.current_token().type == 'ELSE':
            self.consume('ELSE')
            self.consume('{')
            else_block = []
            while self.current_token().type != '}':
                else_block.append(self.parse_statement())
            self.consume('}')
            
        return If(condition, then_block, else_block)
        
    def parse_while(self):
        self.consume('WHILE')
        self.consume('(')
        condition = self.parse_expression()
        self.consume(')')
        self.consume('{')
        
        body = []
        while self.current_token().type != '}':
            body.append(self.parse_statement())
        self.consume('}')
        
        return While(condition, body)
        
    def parse_assignment(self):
        name = self.consume('IDENTIFIER').value
        
        # Check for array assignment
        if self.current_token() and self.current_token().type == '[':
            self.consume('[')
            index = self.parse_expression()
            self.consume(']')
            self.consume('=')
            value = self.parse_expression()
            self.consume(';')
            return ArrayAssignment(name, index, value)
        else:
            self.consume('=')
            expr = self.parse_expression()
            self.consume(';')
            return Assignment(name, expr)
        
    def parse_expression(self):
        return self.parse_comparison()
        
    def parse_comparison(self):
        expr = self.parse_logical()
        return expr
        
    def parse_logical(self):
        expr = self.parse_relational()
        
        while self.current_token() and self.current_token().type in ['&&', '||']:
            op = self.consume().value
            right = self.parse_relational()
            expr = BinaryOp(expr, op, right)
            
        return expr
        
    def parse_relational(self):
        expr = self.parse_arithmetic()
        
        while self.current_token() and self.current_token().type in ['==', '!=', '<', '>', '<=', '>=']:
            op = self.consume().value
            right = self.parse_arithmetic()
            expr = BinaryOp(expr, op, right)
            
        return expr
        
    def parse_arithmetic(self):
        expr = self.parse_term()
        
        while self.current_token() and self.current_token().type in ['+', '-']:
            op = self.consume().value
            right = self.parse_term()
            expr = BinaryOp(expr, op, right)
            
        return expr
        
    def parse_term(self):
        expr = self.parse_factor()
        
        while self.current_token() and self.current_token().type in ['*', '/', '%']:
            op = self.consume().value
            right = self.parse_factor()
            expr = BinaryOp(expr, op, right)
            
        return expr
        
    def parse_factor(self):
        token = self.current_token()
        
        if token.type == 'NUMBER':
            self.consume()
            return Number(token.value)
        elif token.type == 'STRING':
            self.consume()
            return String(token.value)
        elif token.type == 'IDENTIFIER':
            name = self.consume().value
            if self.current_token() and self.current_token().type == '(':
                # Function call
                self.consume('(')
                args = []
                if self.current_token().type != ')':
                    args.append(self.parse_expression())
                    while self.current_token().type == ',':
                        self.consume(',')
                        args.append(self.parse_expression())
                self.consume(')')
                return FunctionCall(name, args)
            elif self.current_token() and self.current_token().type == '[':
                # Array access
                self.consume('[')
                index = self.parse_expression()
                self.consume(']')
                return ArrayAccess(name, index)
            else:
                return Variable(name)
        elif token.type == '(':
            self.consume('(')
            expr = self.parse_expression()
            self.consume(')')
            return expr
        elif token.type == '[':
            # Array literal
            self.consume('[')
            elements = []
            if self.current_token().type != ']':
                elements.append(self.parse_expression())
                while self.current_token().type == ',':
                    self.consume(',')
                    elements.append(self.parse_expression())
            self.consume(']')
            return ArrayLiteral(elements)
        elif token.type == '-':
            # Unary minus
            self.consume('-')
            expr = self.parse_factor()
            return BinaryOp(Number(0), '-', expr)
        else:
            raise SyntaxError(f"Unexpected token in expression: {token.type}")

class ReturnException(Exception):
    def __init__(self, value):
        self.value = value

class Interpreter:
    def __init__(self):
        self.globals = {}
        self.locals_stack = []
        self.functions = {}
        self.arrays = {}  # Store arrays separately
        
    def interpret(self, ast):
        for stmt in ast.statements:
            self.execute(stmt)
            
    def execute(self, node):
        if isinstance(node, FunctionDef):
            self.functions[node.name] = node
        elif isinstance(node, Return):
            value = self.evaluate(node.expr)
            raise ReturnException(value)
        elif isinstance(node, Print):
            value = self.evaluate(node.expr)
            print(value)
        elif isinstance(node, If):
            condition = self.evaluate(node.condition)
            if condition:
                for stmt in node.then_block:
                    self.execute(stmt)
            elif node.else_block:
                for stmt in node.else_block:
                    self.execute(stmt)
        elif isinstance(node, While):
            while self.evaluate(node.condition):
                for stmt in node.body:
                    self.execute(stmt)
        elif isinstance(node, Assignment):
            value = self.evaluate(node.expr)
            if isinstance(value, dict):  # Array literal
                self.arrays[node.name] = value
            else:
                self.set_variable(node.name, value)
        elif isinstance(node, ArrayAssignment):
            array_name = node.array_name
            index = self.evaluate(node.index)
            value = self.evaluate(node.value)
            
            if array_name not in self.arrays:
                self.arrays[array_name] = {}
            self.arrays[array_name][int(index)] = value
        elif isinstance(node, FunctionCall):
            # Function call as statement
            self.call_function(node.name, node.args)
            
    def evaluate(self, node):
        if isinstance(node, Number):
            return node.value
        elif isinstance(node, String):
            return node.value
        elif isinstance(node, Variable):
            return self.get_variable(node.name)
        elif isinstance(node, BinaryOp):
            left = self.evaluate(node.left)
            right = self.evaluate(node.right)
            
            if node.op == '+':
                return left + right
            elif node.op == '-':
                return left - right
            elif node.op == '*':
                if isinstance(left, str) and isinstance(right, int):
                    return left * right
                elif isinstance(left, int) and isinstance(right, str):
                    return left * right
                return left * right
            elif node.op == '/':
                return left / right
            elif node.op == '%':
                return left % right
            elif node.op == '==':
                return left == right
            elif node.op == '!=':
                return left != right
            elif node.op == '<':
                return left < right
            elif node.op == '>':
                return left > right
            elif node.op == '<=':
                return left <= right
            elif node.op == '>=':
                return left >= right
            elif node.op == '&&':
                return left and right
            elif node.op == '||':
                return left or right
        elif isinstance(node, FunctionCall):
            return self.call_function(node.name, node.args)
        elif isinstance(node, ArrayAccess):
            array_name = node.array_name
            index = self.evaluate(node.index)
            
            # Check if it's a string variable
            try:
                string_var = self.get_variable(array_name)
                if isinstance(string_var, str):
                    idx = int(index)
                    if 0 <= idx < len(string_var):
                        return string_var[idx]
                    return ""
            except NameError:
                pass
            
            # Regular array access
            if array_name in self.arrays and int(index) in self.arrays[array_name]:
                return self.arrays[array_name][int(index)]
            else:
                return -sys.maxsize  # Default value for uninitialized array elements
        elif isinstance(node, ArrayLiteral):
            # Return a dictionary representing the array
            result = {}
            for i, element in enumerate(node.elements):
                result[i] = self.evaluate(element)
            return result
            
    def call_function(self, name, args):
        # Built-in functions
        if name == 'len':
            if len(args) != 1:
                raise ValueError("len() takes exactly one argument")
            value = self.evaluate(args[0])
            if isinstance(value, str):
                return len(value)
            elif isinstance(value, dict):  # Array
                return len(value)
            return 0
            
        if name not in self.functions:
            raise NameError(f"Function '{name}' not defined")
            
        func = self.functions[name]
        arg_values = [self.evaluate(arg) for arg in args]
        
        # Create new local scope
        local_vars = {}
        local_arrays = {}
        for i, param in enumerate(func.params):
            if i < len(arg_values):
                value = arg_values[i]
                if isinstance(value, dict):  # Array
                    local_arrays[param] = value
                else:
                    local_vars[param] = value
            else:
                local_vars[param] = None
            
        self.locals_stack.append(local_vars)
        # Store current arrays and add local arrays
        old_arrays = self.arrays.copy()
        self.arrays.update(local_arrays)
        
        try:
            for stmt in func.body:
                self.execute(stmt)
            result = None  # No return statement
        except ReturnException as e:
            result = e.value
        finally:
            self.locals_stack.pop()
            self.arrays = old_arrays
            
        return result
        
    def get_variable(self, name):
        # Check local scope first
        if self.locals_stack:
            local_vars = self.locals_stack[-1]
            if name in local_vars:
                return local_vars[name]
        # Check global scope
        if name in self.globals:
            return self.globals[name]
        # Check arrays
        if name in self.arrays:
            return self.arrays[name]
        raise NameError(f"Variable '{name}' not defined")
        
    def set_variable(self, name, value):
        # Set in local scope if we're in a function
        if self.locals_stack:
            self.locals_stack[-1][name] = value
        else:
            self.globals[name] = value

def main():
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'r') as f:
            code = f.read()
    else:
        code = sys.stdin.read()
        
    lexer = Lexer(code)
    tokens = lexer.tokenize()
    
    parser = Parser(tokens)
    ast = parser.parse()
    
    interpreter = Interpreter()
    interpreter.interpret(ast)

if __name__ == "__main__":
    main()


    