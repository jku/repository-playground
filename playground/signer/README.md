This is a very Work-In-Progress "signing tool" for a git-based TUF-repository


Usage:

# Make sure you have a PIV signing key on your hardware key
https://github.com/secure-systems-lab/securesystemslib/issues/494

# Find the pkcs library (this path works on debian after installing ykcs11)
export PYKCS11LIB=/usr/lib/x86_64-linux-gnu/libykcs11.so

# initialize the repository
./tool init
