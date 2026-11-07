#!/bin/sh
set -eu
mkdir -p build
desk_check_level=''
# Newer cppcheck releases cap normal branch exploration. Request exhaustive
# analysis where available; 2.13 runs the same addon without that newer option.
if cppcheck --help | grep -q -- '--check-level'; then
    desk_check_level='--check-level=exhaustive'
fi
cppcheck --version
cppcheck $desk_check_level --std=c11 --enable=warning,style,performance,portability \
    --error-exitcode=1 --addon=misra --suppress=misra-c2012-8.7 \
    --suppress=misra-c2012-2.5 --inline-suppr --xml --xml-version=2 \
    alert.c 2> build/cppcheck.xml
