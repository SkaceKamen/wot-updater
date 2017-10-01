# wot-updater
CLI tool for updating world of tanks without using launcher

## Warning
This script can break your installation! Use at your own risk! This is very basic script, I mainly used it for updating installation that I never played with, just used for data extraction.
I tested it when downloading 9.17 update and it worked, but this may change in future.

## Requirements
 - 7z
 - rdiff
 - xdelta3
 
## Usage

Best use is to put this script into WoT installation path and just run it. But you can run it from different path too, just use the parameters.

```
usage: update.py [-h] [-p PATH] [-u HOST] [-q]

Updates World of Tanks installation from specified source

optional arguments:
  -h, --help            show this help message and exit
  -p PATH, --path PATH  path to world of tanks installation (default .)
  -u HOST, --host HOST  update host (default loaded from installation path)
  -q, --quiet           suppress output
```
