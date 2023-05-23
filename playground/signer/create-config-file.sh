#!/bin/sh

# Run this script in the folder where the TUF repository resides to
# initialize the config.

set -u
set -e

OS=`uname -s`

echo "Enter your GitHub handle, without '@', e.g. mona"
read GITHUB_HANDLE

case ${OS} in
    Darwin)
        YKSLIB=/opt/homebrew/lib/libykcs11.dylib
    ;;
    Linux)
        YKSLIB=/usr/lib/x86_64-linux-gnu/libykcs11.so
        ;;
    *)
        echo Unsupported OS ${OS}
        exit 1
    ;;
esac

if [ ! -f ${YKSLIB} ]; then
    echo "Could not find a PKCS library at path ${YKSLIB}"
    echo "Please install a PKCS library, or enter a path where one is installed:"
    read YKSLIB
    echo "Using ${YKSLIB}. This can changed later via 'pykcs11lib' in file .playground-sign.ini"
fi

cat > .playground-sign.ini <<EOF
[settings]
# Path to PKCS#11 module
pykcs11lib = ${YKSLIB}
# GitHub username
user-name = @${GITHUB_HANDLE}

# Git remotes
pull-remote = origin
push-remote = origin
EOF
