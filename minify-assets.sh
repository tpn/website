#!/bin/bash

# Directory containing the output files
OUTPUT_DIR="docs"

# Minify HTML files
find "$OUTPUT_DIR" -name "*.html" -exec html-minifier-terser --collapse-whitespace --remove-comments --remove-optional-tags --minify-js true --minify-css true --output {} {} \;

# Minify CSS files
#find "$OUTPUT_DIR" -name "*.css" -exec cssnano {} {} \;

# Minify JavaScript files
find "$OUTPUT_DIR" -name "*.js" -exec terser --compress --mangle --output {} -- {} \;

