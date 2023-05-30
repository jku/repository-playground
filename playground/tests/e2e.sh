#!/bin/bash

# Run a end-to-end test of repository-playground locally
# This emulates:
# * GitHub Actions
# * Hardware signing
# * Online signing
#
# System dependencies
# * libfaketime
# * softhsm2
#
# For macOS users, those dependencies are available via Homebrew:
# $ brew install softhsm swig libfaketime
#
# Python dependencies
# * signer: pip install ./playground/signer/
# * repo: pip install ./playground/repo/
# * pynacl: pip install pynacl  # for the testing ed25519 key
#
#
# Set DEBUG_TESTS=1 for more visibility. This will leave the temp directories in place.
# The directory contents will be as below:
# <TESTNAME>
#   + publish/ -- the final published metadata directory
#                 (note that signatures are wiped to make diffing easier: ECDSA sigs are not deterministic)
#   + git/     -- the upstream (bare) git repository
#   + repo/
#      + git/ -- the repository used for emulate GitHub Actions, like snapshot
#   + signer/
#      + git/ -- the repository used to emulate human user running playground-delegate and sign

set -euo pipefail

DEBUG_TESTS=${DEBUG_TESTS:-}

if [ ! -z ${DEBUG_TESTS} ]; then
    set -x
fi

function cleanup {
    EXIT_CODE=$?
    if [ ! -z ${DEBUG_TESTS} ]; then
        ls $WORK_DIR
        if [[ $EXIT_CODE -ne 0 ]]; then
          echo "signer STDOUT:"
          sed 's/^/| /' $SIGNER_DIR/out || true
          echo "repo STDOUT:"
          sed 's/^/| /' $REPO_DIR/out || true
        fi
    else
        rm -rf "$WORK_DIR"
    fi
    if [[ $EXIT_CODE -ne 0 ]]; then
        echo "Failed"
    fi
}
trap cleanup EXIT

strip_signatures()
{
    sed -ie2e -E -e 's/"sig": ".+"/"sig": "XXX"/' $1
    # Remove backup file
    rm "$1e2e"
}

git_repo()
{
    git \
        -C $REPO_GIT \
        -c user.name=repository-playground \
        -c user.email=41898282+github-actions[bot]@users.noreply.github.com \
        -c commit.gpgsign=false \
        $@
}

repo_setup()
{
    # init upstream repo
    git -C $UPSTREAM_GIT init --quiet --bare --initial-branch=main

    # Clone upstream to repo, create a dummy commit so merges are possible
    git_repo clone --quiet $UPSTREAM_GIT . 2>/dev/null
    touch $REPO_GIT/.dummy $REPO_DIR/out
    git_repo add .dummy
    git_repo commit -m "init" --quiet
    git_repo push --quiet
}

signer_setup()
{
    USER=$1
    SIGNER_DIR="$WORK_DIR/$TEST_NAME/$USER"
    SIGNER_GIT="$SIGNER_DIR/git"

    mkdir -p $SIGNER_GIT

    # initialize softhsm: Make it look like we have HW key attached
    echo "directories.tokendir = $SIGNER_DIR/tokens" > "$SIGNER_DIR/softhsm2.conf"
    cp -r $SCRIPT_DIR/softhsm/tokens-$USER $SIGNER_DIR/tokens

    # clone the test repository
    git -C $SIGNER_GIT clone --quiet $UPSTREAM_GIT .
    git -C $SIGNER_GIT config user.email "$USER@example.com"
    git -C $SIGNER_GIT config user.name "$USER"

    # Set user configuration
    echo -e "[settings]\n" \
         "pykcs11lib = $SOFTHSMLIB\n" \
         "user-name = @playground$USER\n" \
         "push-remote = origin\n" \
         "pull-remote = origin\n" > $SIGNER_GIT/.playground-sign.ini
}

signer_init()
{
    # run playground-delegate: creates a commit, pushes it to remote branch
    USER=$1
    EVENT=$2

    SIGNER_DIR="$WORK_DIR/$TEST_NAME/$USER"
    SIGNER_GIT="$SIGNER_DIR/git"
    export SOFTHSM2_CONF="$SIGNER_DIR/softhsm2.conf"

    INPUT=(
        ""                  # Configure root ? [enter to continue]
        ""                  # Configure targets? [enter to continue]
        "1"                 # Configure online roles? [1: configure key]
        "4"                 # Enter key id
        ""                  # Configure online roles? [enter to continue]
        "2"                 # Choose signing key [2: yubikey]
        ""                  # Insert HW key and press enter
        "0000"              # sign root
        "0000"              # sign root
        "0000"              # sign targets
        "0000"              # sign root
        ""                  # press enter to push
    )

    cd $SIGNER_GIT

    for line in "${INPUT[@]}"; do
        echo $line
    done | playground-delegate $EVENT >> $SIGNER_DIR/out 2>&1
}

signer_init_shorter_snapshot_expiry()
{
    # run playground-delegate: creates a commit, pushes it to remote branch
    USER=$1
    EVENT=$2

    SIGNER_DIR="$WORK_DIR/$TEST_NAME/$USER"
    SIGNER_GIT="$SIGNER_DIR/git"
    export SOFTHSM2_CONF="$SIGNER_DIR/softhsm2.conf"

    INPUT=(
        ""                  # Configure root ? [enter to continue]
        ""                  # Configure targets? [enter to continue]
        "1"                 # Configure online roles? [1: configure key]
        "4"                 # Enter key id
        "3"                 # Configure online roles? [3: configure snapshot]
        "10"                # Enter expiry [10 days]
        "4"                 # Enter signing period [4 days]
        ""                  # Configure online roles? [enter to continue]
        "2"                 # Choose signing key [2: yubikey]
        ""                  # Insert HW key and press enter
        "0000"              # sign root
        "0000"              # sign root
        "0000"              # sign targets
        "0000"              # sign root
        ""                  # press enter to push
    )

    cd $SIGNER_GIT

    for line in "${INPUT[@]}"; do
        echo $line
    done | playground-delegate $EVENT >> $SIGNER_DIR/out 2>&1
}

signer_init_multiuser()
{
    # run playground-delegate: creates a commit, pushes it to remote branch
    USER=$1
    EVENT=$2

    SIGNER_DIR="$WORK_DIR/$TEST_NAME/$USER"
    SIGNER_GIT="$SIGNER_DIR/git"
    export SOFTHSM2_CONF="$SIGNER_DIR/softhsm2.conf"

    INPUT=(
        ""                  # Configure root? [enter to continue]
        "1"                 # Configure targets? [1: configure signers]
        "@playgrounduser1, @playgrounduser2" # Enter signers
        "2"                 # Enter threshold
        ""                  # Configure targets? [enter to continue]
        "1"                 # Configure online roles? [1: configure key]
        "4"                 # Enter key id
        ""                  # Configure online roles? [enter to continue]
        "2"                 # Choose signing key [2: yubikey]
        ""                  # Insert HW key and press enter
        "0000"              # sign root
        "0000"              # sign root
        ""                  # press enter to push
    )

    cd $SIGNER_GIT

    for line in "${INPUT[@]}"; do
        echo $line
    done | playground-delegate $EVENT >> $SIGNER_DIR/out 2>&1
}

signer_accept_invite()
{
    # run playground-sign: creates a commit, pushes it to remote branch
    USER=$1
    EVENT=$2

    SIGNER_DIR="$WORK_DIR/$TEST_NAME/$USER"
    SIGNER_GIT="$SIGNER_DIR/git"
    export SOFTHSM2_CONF="$SIGNER_DIR/softhsm2.conf"

    INPUT=(
        "2"                 # Choose signing key [2: yubikey]
        ""                  # Insert HW and press enter
        "0000"              # sign targets
        "0000"              # sign targets
        ""                  # press enter to push
    )

    cd $SIGNER_GIT

    for line in "${INPUT[@]}"; do
        echo $line
    done | playground-sign $EVENT >> $SIGNER_DIR/out 2>&1

}

signer_sign()
{
    # run playground-sign: creates a commit, pushes it to remote branch
    USER=$1

    EVENT=$2

    SIGNER_DIR="$WORK_DIR/$TEST_NAME/$USER"
    SIGNER_GIT="$SIGNER_DIR/git"
    export SOFTHSM2_CONF="$SIGNER_DIR/softhsm2.conf"

    INPUT=(
        "0000"              # sign the role
        ""                  # press enter to push
    )

    cd $SIGNER_GIT

    for line in "${INPUT[@]}"; do
        echo $line
    done | playground-sign $EVENT >> $SIGNER_DIR/out 2>&1
}

signer_add_targets()
{
    USER=$1
    EVENT=$2

    SIGNER_DIR="$WORK_DIR/$TEST_NAME/$USER"
    SIGNER_GIT="$SIGNER_DIR/git"
    export SOFTHSM2_CONF="$SIGNER_DIR/softhsm2.conf"

    cd $SIGNER_GIT

    # Make target file changes, push to remote signing event branch
    git fetch --quiet origin
    git switch --quiet -C $EVENT origin/main
    mkdir -p targets
    echo "file1" > targets/file1.txt
    echo "file2" > targets/file2.txt
    git add targets/file1.txt targets/file2.txt
    git commit  --quiet -m "Add 2 target files"
    git push --quiet origin $EVENT
}

signer_modify_targets()
{
    USER=$1
    EVENT=$2

    SIGNER_DIR="$WORK_DIR/$TEST_NAME/$USER"
    SIGNER_GIT="$SIGNER_DIR/git"
    export SOFTHSM2_CONF="$SIGNER_DIR/softhsm2.conf"

    cd $SIGNER_GIT

    # Make target file changes, push to remote signing event branch
    git fetch --quiet origin
    git switch --quiet $EVENT
    echo "file1 modified" > targets/file1.txt
    git rm --quiet targets/file2.txt
    git add targets/file1.txt
    git commit  --quiet -m "Modify target files"
    git push --quiet origin $EVENT
}


repo_merge()
{
    EVENT=$1

    # update repo from upstream and merge the event branch
    git_repo switch --quiet main
    git_repo fetch --quiet origin
    git_repo merge --quiet origin/$EVENT

    # run playground-status to check that all is ok
    cd $REPO_GIT
    playground-status >> $REPO_DIR/out

    git_repo push --quiet
}

repo_status_fail()
{
    EVENT=$1

    # update repo from upstream and merge the event branch
    git_repo fetch --quiet origin
    git_repo checkout --quiet $EVENT
    git_repo pull --quiet

    # run playground-status, expect failure
    # Note that playground-status may make a commit (to modify targets metadata) even if end result is failure
    # TODO: check output for specifics
    cd $REPO_GIT

    if playground-status >> $REPO_DIR/out; then
        return 1
    fi
    git_repo checkout --quiet main
}

repo_snapshot()
{
    git_repo switch --quiet main
    git_repo pull --quiet

    cd $REPO_GIT


    if LOCAL_TESTING_KEY=$ONLINE_KEY playground-snapshot --push $PUBLISH_DIR >> $REPO_DIR/out 2>&1; then
        echo "generated=true" >> $REPO_DIR/out
    else
        echo "generated=false" >> $REPO_DIR/out
    fi
}

repo_bump_versions()
{
    git_repo switch --quiet main
    git_repo pull --quiet

    cd $REPO_GIT

    if LOCAL_TESTING_KEY=$ONLINE_KEY playground-bump-online --push $PUBLISH_DIR >> $REPO_DIR/out 2>&1; then
        echo "generated=true" >> $REPO_DIR/out
    else
        echo "generated=false" >> $REPO_DIR/out
    fi

    events=$(playground-bump-offline --push)
    echo "events=$events"  >> $REPO_DIR/out

    # TODO: run signing events
}

setup_test() {
    TEST_NAME=$1

    # These variables are used by all setup and test methods
    PUBLISH_DIR=$WORK_DIR/$TEST_NAME/publish
    UPSTREAM_GIT="$WORK_DIR/$TEST_NAME/git"
    REPO_DIR="$WORK_DIR/$TEST_NAME/repo"
    REPO_GIT="$REPO_DIR/git"

    mkdir -p $REPO_GIT $UPSTREAM_GIT $PUBLISH_DIR

    repo_setup
    signer_setup "user1"
    signer_setup "user2"
}

test_basic()
{
    echo -n "Basic repository initialization... "
    setup_test "basic"

    # Run the processes under test
    # user1: Start signing event, sign root and targets
    signer_init user1 sign/initial
    # merge successful signing event, create snapshot
    repo_merge sign/initial
    repo_snapshot
    repo_bump_versions # no-op expected

    # Verify test result
    # ECDSA signatures are not deterministic: wipe all sigs so diffing is easy
    for t in ${PUBLISH_DIR}/metadata/*.json; do
        strip_signatures $t
    done
    # the resulting metadata should match expected metadata exactly
    diff -r $SCRIPT_DIR/expected/basic/ $PUBLISH_DIR

    echo "OK"
}

test_online_bumps()
{
    echo -n "Online version bump... "
    setup_test "online-version-bump"

    # Run the processes under test
    # user1: Start signing event, set snapshot expiry at 10 days, sign root and targets
    signer_init_shorter_snapshot_expiry user1 sign/initial
    # merge successful signing event, create snapshot
    repo_merge sign/initial
    repo_snapshot
    # run three version bumps
    repo_bump_versions # no-op expected
    FAKETIME="2021-02-14 01:02:03"
    repo_bump_versions # 11 days forward: snapshot v2 and timestamp v2 expected
    FAKETIME="2021-02-16 01:02:03"
    repo_bump_versions # 2 more days forward: timestamp v3 expected
    FAKETIME="2021-02-03 01:02:03"

    # Verify test result
    # ECDSA signatures are not deterministic: wipe all sigs so diffing is easy
    for t in ${PUBLISH_DIR}/metadata/*.json; do
        strip_signatures $t
    done
    # the resulting metadata should match expected metadata exactly
    diff -r $SCRIPT_DIR/expected/online-version-bump/ $PUBLISH_DIR

    echo "OK"
}

test_multi_user_signing()
{
    echo -n "Multiuser signing... "
    setup_test "multi-user-signing"

    # Run the processes under test
    # user1: Start signing event, invite user2
    signer_init_multiuser user1 sign/initial
    repo_status_fail sign/initial
    # user2: accept invite, sign root & targets
    signer_accept_invite user2 sign/initial
    repo_status_fail sign/initial
    # user1: sign root & targets
    signer_sign user1 sign/initial
    # merge successful signing event, create new snapshot
    repo_merge sign/initial
    repo_snapshot


    # Verify test result
    # ECDSA signatures are not deterministic: wipe all sigs so diffing is easy
    for t in ${PUBLISH_DIR}/metadata/*.json; do
        strip_signatures $t
    done
    # the resulting metadata should match expected metadata exactly
    diff -r $SCRIPT_DIR/expected/multi-user-signing/ $PUBLISH_DIR

    echo "OK"
}

test_target_changes()
{
    echo -n "Target file changes... "
    setup_test "target-file-changes"

    # This first section is identical to multi-user-signing
    # user1: Start signing event, invite user2 as second targets signer
    signer_init_multiuser user1 sign/initial
    repo_status_fail sign/initial
    # user2: accept invite, sign targets
    signer_accept_invite user2 sign/initial
    repo_status_fail sign/initial
    # user1: sign root & targets
    signer_sign user1 sign/initial

    # merge successful signing event, create new snapshot
    repo_merge sign/initial
    repo_snapshot

    # This section modifies targets in a new signing event
    # User 1 adds target files, repository modifies metadata, user 1 signs
    signer_add_targets user1 sign/new-targets
    repo_status_fail sign/new-targets
    signer_sign user1 sign/new-targets

    # user2: delete one target, modify another. repo modifies metadata, user2 signs
    signer_modify_targets user2 sign/new-targets
    repo_status_fail sign/new-targets
    signer_sign user2 sign/new-targets

    # user1: original signature is no longer valid: sign again
    signer_sign user1 sign/new-targets

    # merge successful signing event, create new snapshot
    repo_merge sign/new-targets
    repo_snapshot

    # Verify test result
    # ECDSA signatures are not deterministic: wipe all sigs so diffing is easy
    for t in ${PUBLISH_DIR}/metadata/*.json; do
        strip_signatures $t
    done
    # the resulting metadata should match expected metadata exactly
    diff -r $SCRIPT_DIR/expected/target-file-changes/ $PUBLISH_DIR

    echo "OK"
}


OS=$(uname -s)

# run the tests under a fake time
case ${OS} in
    Darwin)
        export DYLD_INSERT_LIBRARIES=/opt/homebrew/lib/faketime/libfaketime.1.dylib
        export DYLD_FORCE_FLAT_NAMESPACE=1
        SOFTHSMLIB=/opt/homebrew/lib/softhsm/libsofthsm2.so
        ;;
    Linux)
        export LD_PRELOAD=/usr/lib/x86_64-linux-gnu/faketime/libfaketime.so.1
        SOFTHSMLIB="/usr/lib/softhsm/libsofthsm2.so"
        ;;
    *)
        echo "Unsupported os ${OS}"
        exit 1
        ;;
esac

export FAKETIME="2021-02-03 01:02:03"
export TZ="UTC"

WORK_DIR=$(mktemp -d)
SCRIPT_DIR=$(dirname $(readlink -f "$0"))

ONLINE_KEY="1d9a024348e413892aeeb8cc8449309c152f48177200ee61a02ae56f450c6480"

# Run tests
test_basic
test_online_bumps
test_multi_user_signing
test_target_changes
