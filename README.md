# Conan Barbarian Style

This project is a command line tool to identify dependencies between compiled Linux libraries in order to compile C++ software. The main reason is that GCC requires the libraries to be listed in topological order, otherwise the link step fails.

The tool can
- analyze static and dynamic libraries to extract exported and required symbols
- sort a list of libraries in topological order according to their dependencies
- search which of the analyzed library defines a symbol
- print the entire dependencies graph
- generate a python function compatible with conan to define components and dependencies among components

Disclaimer: the tool has not been extensively tested, I stopped working on it as soon as it produced a result good enough for my use case, and I will not improve nor maintain it.
