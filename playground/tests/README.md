# End-to-end tests for repository-playground

Repository-playground is implemented on top of a CI system, git and quite a bit of
user interaction (through both the CI system and the signing tools). This makes
testing tricky. These tests are an attempt at defining a set of functionality that
can be tested without
* Github issues being created
* git branches modified on github.com
* sigstore or Google Cloud signing for online keys
* a user signing with a Yubikey

The rough layout of repository-playground is:
1. Users run a set of python programs (see playground/signer/)
2. **These programs modify metadata stored in git, commit the changes into git and push various branches to upstream**
3. Github workflows react to triggers (cron, push) and call GitHub actions defined in repository-playground
4. The GitHub actions run a separate set of python programs (see playground/repo/)
5. **These programs also modify metadata stored in git, commit changes and push various branches**

The tests are designed to test steps 2 and 5 and emulate steps 1, 3 and 4. The purpose is to make
refactoring and development of the python programs easier (because they have test coverage). In
practice:
* functions named `signer_*()` emulate user interactions with tools in playground/signer/ (`playground-sign`, `playground-delegate`).
* functions name `repo_*()` emulate GitHub workflows and actions using the tools in playground/repo/
* The signer functions operate within one git repository, the repo functions in another: both of them
  push to and pull from the "upstream" git repository. In this test setup all of these git repositories are local
* Yubikeys are simulated with SoftHSM2
* Online signing is simulated with a hack that uses a environment variable private key instead of sigstore or GCP
* simulated user input is handled by a bash array that is fed to STDIN of the signer tool
* libfaketime is used to ensure the expiry times in the metadata are predictable

The main thing being verified in the tests is the final "publishable" metadata repository -- the resulting git repository
structure would be nice to verify as well but unfortunately the nondeterministic ECDSA signatures make that tricky.

## Requirements
* System (Linux)
  ```sh
  apt install softhsm2 swig libfaketime
  ```
* System (macOS)
  ```sh
  brew install softhsm swig libfaketime
  ```
* Python
  ```sh
  pip install -e ../signer/ && pip install -e ../repo/
  ```

## Issues
* Hard to see what is happening in a test (`DEBUG_TESTS=1 ./e2e.sh` helps but is still not great)
* Hard-coded shared library paths for `libsofthsm2` and `libfaketime` need to be changed in `e2e.sh`, if not installed in
  a standard location.
* On macOS `libfaketime` does not work, if using system Python and SIP is enabled (default). You may try using a custom
  Python installation, e.g. from `brew`. For more infos, see 
  [libfaketime/README.OSX](https://github.com/wolfcw/libfaketime/blob/master/README.OSX).
* The whole rig is a hack to get something running, not a real test setup.
  Could consider using https://github.com/bats-core/bats-core or similar
  if the core idea seems viable.
