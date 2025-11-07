#!/bin/bash

function install_from_requirements() {
    local dir=$1
    for file in "$dir"/*; do
        if [ -d "$file" ]; then
            install_from_requirements "$file"
        elif [ "$file" == "$dir/requirements.txt" ]; then
            echo "Installing packages from $file"
            pip install -r "$file"
        fi
    done
}

install_from_requirements "plugins"

python3 main.py