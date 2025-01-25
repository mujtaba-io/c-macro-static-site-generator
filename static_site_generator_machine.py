import os
import re
import shutil
from typing import Dict, Set, List, Optional
from dataclasses import dataclass
from enum import Enum, auto

class PreprocessorError(Exception):
    pass

class TokenType(Enum):
    INCLUDE = auto()
    DEFINE = auto()
    IFDEF = auto()
    IFNDEF = auto()
    ELSE = auto()
    ENDIF = auto()
    UNDEF = auto()
    TEXT = auto()

@dataclass
class Token:
    type: TokenType
    value: str
    line_number: int
    file: str

@dataclass
class Macro:
    name: str
    params: List[str]
    body: str
    file: str
    line: int

class Preprocessor:
    def __init__(self):
        self.build_dir = "build"
        self.include_stack: List[str] = []
        self.macros: Dict[str, Macro] = {}
        self.defined_symbols: Set[str] = set()
        self.conditional_stack: List[bool] = []

    def collect_macro_body(self, lines: List[str], start_idx: int) -> tuple[str, int]:
        """Collects a macro body between parentheses."""
        body = []
        paren_count = 0
        i = start_idx
        
        while i < len(lines):
            line = lines[i].rstrip()
            
            for char in line:
                if char == '(':
                    paren_count += 1
                elif char == ')':
                    paren_count -= 1
            
            if paren_count > 0:
                body.append(line)
                i += 1
            elif paren_count == 0 and ')' in line:
                # Get content up to the closing parenthesis
                body.append(line[:line.rindex(')')])
                break
            else:
                raise PreprocessorError(f"Unmatched parentheses in macro definition")
            
        return '\n'.join(body), i

    def tokenize(self, content: str, filename: str) -> List[Token]:
        lines = content.split('\n')
        tokens = []
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            
            if not line:
                i += 1
                continue
                
            if line.startswith('#include'):
                match = re.match(r'#include\s*[<"](.+)[>"]', line)
                if match:
                    tokens.append(Token(TokenType.INCLUDE, match.group(1), i + 1, filename))
                i += 1
                continue
            
            if line.startswith('#define'):
                match = re.match(r'#define\s+(\w+)(?:\(([\w\s,]*)\))?\s*\(', line)
                if match:
                    name, params = match.groups()
                    params = [p.strip() for p in params.split(',')] if params else []
                    
                    # Collect the macro body until matching closing parenthesis
                    body, end_line = self.collect_macro_body(lines, i)
                    tokens.append(Token(TokenType.DEFINE, (name, params, body), i + 1, filename))
                    i = end_line + 1
                    continue
            
            if line.startswith('#ifdef'):
                match = re.match(r'#ifdef\s+(\w+)', line)
                if match:
                    tokens.append(Token(TokenType.IFDEF, match.group(1), i + 1, filename))
                i += 1
                continue
                
            if line.startswith('#ifndef'):
                match = re.match(r'#ifndef\s+(\w+)', line)
                if match:
                    tokens.append(Token(TokenType.IFNDEF, match.group(1), i + 1, filename))
                i += 1
                continue
            
            if line.startswith('#else'):
                tokens.append(Token(TokenType.ELSE, '', i + 1, filename))
                i += 1
                continue
                
            if line.startswith('#endif'):
                tokens.append(Token(TokenType.ENDIF, '', i + 1, filename))
                i += 1
                continue
                
            if line.startswith('#undef'):
                match = re.match(r'#undef\s+(\w+)', line)
                if match:
                    tokens.append(Token(TokenType.UNDEF, match.group(1), i + 1, filename))
                i += 1
                continue
            
            # Handle text with possible macro calls
            if '(' in line:
                # Check if this is the start of a multi-line macro call
                match = re.match(r'(\w+)\s*\(', line)
                if match and match.group(1) in self.macros:
                    body, end_line = self.collect_macro_body(lines[i:], 0)
                    tokens.append(Token(TokenType.TEXT, f"{match.group(1)}({body})", i + 1, filename))
                    i += end_line + 1
                    continue
            
            tokens.append(Token(TokenType.TEXT, line, i + 1, filename))
            i += 1
            
        return tokens

    def parse_macro_args(self, args_text: str) -> List[str]:
        """Parse macro arguments handling multi-line arguments."""
        args = []
        current_arg = []
        paren_count = 0
        lines = args_text.split('\n')
        
        for line in lines:
            line = line.strip()
            
            for char in line:
                if char == '(':
                    paren_count += 1
                    current_arg.append(char)
                elif char == ')':
                    paren_count -= 1
                    current_arg.append(char)
                elif char == ',' and paren_count == 0:
                    if current_arg:
                        args.append(''.join(current_arg).strip())
                        current_arg = []
                else:
                    current_arg.append(char)
        
        if current_arg:
            args.append(''.join(current_arg).strip())
        
        return [arg.strip() for arg in args if arg.strip()]

    def expand_macro(self, macro: Macro, args: List[str]) -> str:
        """
        Expand a macro with given arguments, replacing only variables enclosed in curly braces.
        Example: {param} will be replaced, but param by itself won't be.
        """
        if len(args) != len(macro.params):
            raise PreprocessorError(
                f"Macro '{macro.name}' expects {len(macro.params)} arguments, "
                f"but got {len(args)} in file {macro.file} at line {macro.line}"
            )
        
        result = macro.body
        for param, arg in zip(macro.params, args):
            # Only replace parameters that are enclosed in curly braces
            pattern = r'\{' + re.escape(param) + r'\}'
            result = re.sub(pattern, arg, result)
        return result

    def process_tokens(self, tokens: List[Token], base_dir: str) -> str:
        # First pass: collect all macro definitions
        self.collect_macros(tokens, base_dir)
        
        # Second pass: process content
        output = []
        i = 0
        
        while i < len(tokens):
            token = tokens[i]
            
            if self.conditional_stack and not self.conditional_stack[-1]:
                if token.type in {TokenType.ENDIF, TokenType.ELSE}:
                    self.handle_conditional_directive(token)
                i += 1
                continue
            
            if token.type == TokenType.INCLUDE:
                output.append(self.process_include(token, base_dir))
            elif token.type == TokenType.TEXT:
                output.append(self.process_text(token))
            elif token.type in {TokenType.IFDEF, TokenType.IFNDEF, TokenType.ELSE, TokenType.ENDIF}:
                self.handle_conditional_directive(token)
            elif token.type == TokenType.UNDEF:
                if token.value in self.macros:
                    del self.macros[token.value]
                self.defined_symbols.discard(token.value)
            
            i += 1
        
        return '\n'.join(filter(None, output))

    def collect_macros(self, tokens: List[Token], base_dir: str) -> None:
        for token in tokens:
            if token.type == TokenType.DEFINE:
                name, params, body = token.value
                self.macros[name] = Macro(name, params, body, token.file, token.line_number)
                self.defined_symbols.add(name)
            elif token.type == TokenType.INCLUDE:
                self.process_include_macros(token, base_dir)

    def process_include_macros(self, token: Token, base_dir: str) -> None:
        include_path = os.path.normpath(
            os.path.join(os.path.dirname(token.file), token.value)
        )
        
        if include_path in self.include_stack:
            raise PreprocessorError(
                f"Circular inclusion detected:\n" +
                "\n".join(f"  {f}" for f in self.include_stack + [include_path])
            )
        
        self.include_stack.append(include_path)
        try:
            with open(include_path, 'r', encoding='utf-8') as f:
                included_content = f.read()
            included_tokens = self.tokenize(included_content, include_path)
            self.collect_macros(included_tokens, base_dir)
        finally:
            self.include_stack.pop()

    def process_include(self, token: Token, base_dir: str) -> str:
        include_path = os.path.normpath(
            os.path.join(os.path.dirname(token.file), token.value)
        )
        
        self.include_stack.append(include_path)
        try:
            with open(include_path, 'r', encoding='utf-8') as f:
                included_content = f.read()
            included_tokens = self.tokenize(included_content, include_path)
            return self.process_tokens(included_tokens, base_dir)
        finally:
            self.include_stack.pop()

    def process_text(self, token: Token) -> str:
        line = token.value
        for macro_name, macro in self.macros.items():
            pattern = rf'{macro_name}\s*\(((?:[^()]*|\([^()]*\))*)\)'
            match = re.search(pattern, line)
            if match:
                args = self.parse_macro_args(match.group(1))
                expansion = self.expand_macro(macro, args)
                line = line[:match.start()] + expansion + line[match.end():]
        return line

    def handle_conditional_directive(self, token: Token):
        if token.type == TokenType.IFDEF:
            self.conditional_stack.append(token.value in self.defined_symbols)
        elif token.type == TokenType.IFNDEF:
            self.conditional_stack.append(token.value not in self.defined_symbols)
        elif token.type == TokenType.ELSE:
            if not self.conditional_stack:
                raise PreprocessorError("#else without matching #if")
            self.conditional_stack[-1] = not self.conditional_stack[-1]
        elif token.type == TokenType.ENDIF:
            if not self.conditional_stack:
                raise PreprocessorError("#endif without matching #if")
            self.conditional_stack.pop()

    def process_file(self, filepath: str, base_dir: str) -> str:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        tokens = self.tokenize(content, filepath)
        return self.process_tokens(tokens, base_dir)

    def generate_site(self, source_dir: str = ".") -> None:
        if os.path.exists(self.build_dir):
            shutil.rmtree(self.build_dir)
        os.makedirs(self.build_dir)
        
        for root, _, files in os.walk(source_dir):
            if self.build_dir in root.split(os.sep):
                continue
                
            for file in files:
                if file.endswith('.py'):
                    continue
                    
                source_path = os.path.join(root, file)
                rel_path = os.path.relpath(source_path, source_dir)
                build_path = os.path.join(self.build_dir, rel_path)
                
                os.makedirs(os.path.dirname(build_path), exist_ok=True)

                if not file.endswith('.html'):
                    shutil.copy(source_path, build_path)
                else:
                    try:
                        processed_content = self.process_file(source_path, source_dir)
                        with open(build_path, 'w', encoding='utf-8') as f:
                            f.write(processed_content)
                    except Exception as e:
                        print(f"Error processing {source_path}:")
                        print(f"  {str(e)}")

def main():
    print("C-Style Macro Static Site Generator")
    print("==================================")
    
    preprocessor = Preprocessor()
    try:
        preprocessor.generate_site()
        print(f"\nSite generated successfully in '{preprocessor.build_dir}' directory!")
    except Exception as e:
        print(f"Fatal error: {str(e)}")
        exit(1)

if __name__ == "__main__":
    main()