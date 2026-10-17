# Releasing

For whoever maintains Zīj. Users never need this page; builders have
`BUILD_NOTES.md`.

## What the public repository carries

The app, its tests, four documents — this one, `BUILD_NOTES.md`,
`REFERENCES.md` and `HOSTILE_PASS_CHECKLIST.md` — and `tools/git-hooks/`,
which carries the one hook described below. The development repository also
holds maintainer tooling that reads those private notes; it is listed in
`tools/private-paths.txt`, step 3 below leaves it out of the drop, and the hook
refuses any drop whose tree is not the tested commit's less the paths that list
names, on `main` or at the tested commit. Nothing
else — no build logs, no change notes, no audit reports, no working notes, and
no development history. Comments in the source that cite `process/` records
are pointing at the maintainer's private notes, which is where all of that
lives; they are not public and are not meant to be.

**Before adding a file to the published tree, and before writing anything
that will land there, ask whether it should be readable by anyone,
forever.** That covers a commit message and a release note as much as a
file: the public repository's history is one commit per release, so a
message written there is a permanent part of the published project. If the
answer is anything but a clear yes, it belongs in the development repository
or the private notes instead.

## Where things live

- **The development repository, private.** Every branch, pull request and test run is here.
  Nothing about it is public.
- **`dar-al-hikma/Zij`, public** — the published project. It carries **one commit per release**,
  whose tree is the source that release's binaries were built from, plus the tag and the
  release itself. No branches, no development history. The AGPL asks that a binary's
  corresponding source be available, and this is that source; it does not ask for the history
  by which the source was written.
- **The backup**, private, is a redundant copy of the development repository written by the
  backup routine alone; never develop there.
- **The texts** are not in the repository and never will be: they are copyrighted translations,
  worked from privately. Nothing in a release or a workflow may copy them.

## The routine

Every change reaches `main` by pull request; `main` has a ruleset (no force-push, no deletion,
PR required, the `pytest` check required, no bypass). Merge when the check is green.

**Install the hook first, in every fresh clone:**

```bash
git config core.hooksPath tools/git-hooks
```

`tools/git-hooks/pre-push` refuses any push whose target is the public repository unless
`ZIJ_PUBLIC_DROP=1` is set. It matches the remote by URL as well as by name, so
`git push <url>` is caught too, whatever the URL's case, doubled slashes, dot segments,
percent-encoding, or query or fragment after it, and the public repository's wiki with it; it
leaves the development repository and the backup alone. On a push to the public repository it
first fetches `origin` and, when `origin/main`'s copy of the hook differs from the checkout's,
runs that copy instead, so the brake always applies `main`'s current checks, and it refuses the
push when it cannot fetch or read that copy. Step 3 below is the only place it is meant to be
bypassed. A clone without that `git config` line, or a checkout at a commit without the hook
file, has no brake at all, so set it before anything else. The brake is advisory:
`git push --no-verify` skips it too, and nothing done on GitHub itself, in its web pages or
through its API, ever passes it.

1. **Test a build without releasing.** Actions → *Build Desktop App* → *Run workflow* → `main`.
   About ten minutes later the run page has two artifacts (`Zij-Windows`,
   `-macOS`), kept three days, no release made. GitHub wraps an artifact in its own zip on
   download, so the Windows one unzips to `Zij-windows.zip`; unzip
   again. The tag's build installs the same locked packages, but it is a build of its own, not a
   byte-for-byte copy of this one: the runner images, the Python patch release and the three
   packages compiled on the runner can move between the two, so the tag's build runs the same
   checks again.
2. **Set the version.** `APP_VERSION` in `engine.py` (section 0) is the tag without its `v`
   and without `-dev` — set it to `1.0.0` and merge that before tagging `v1.0.0`, then put it
   back to `<next>-dev`. It is written into every saved record, but not into an exported
   analysis, and it is printed on the Sources page's citation-key line — the one place a page
   carries it. The hook refuses a drop whose `APP_VERSION` is not the version it is released as.
   The clock does not count a change to that one line as drift from the citation register.

### Before every release: the security checklist

Tick each line for the commit being released, not for your checkout.

**The drop**

1. Build the drop in a fresh clone of the development repository at the tested, merged commit,
   never in a working checkout: no untracked file can then enter it. Then compare its tree with
   the list of published paths. Every file in the drop is the project's own work, or third-party
   material whose licence allows it, and something in the drop uses it.
2. The drop's commit message and the tag's message are exactly `Zīj (زِيج) vX.Y.Z`. The release
   note is written by hand, and it, the commit, the tag and every file — binary files included —
   have been searched for the private texts' page markers and for private names and paths.
3. The release gate has judged the commit being pushed, with the texts present, and the full
   suite has passed in a clean clone of the drop without them.

**The program a stranger runs**

4. Started from a folder holding a hostile `.streamlit/config.toml`, and with one in the home
   folder, the server still refuses a foreign `Origin`, a foreign `Host` and a client without the
   window's per-launch secret. That client is shown one sentence and no traceback: it is stopped
   before the app runs past its imports. An error's full detail is shown in the window alone, as
   the launcher's command line sets it, which no config file can change.
5. Under umask 000, the data folder is created owner-only, and an existing one this account owns
   is narrowed to owner-only; a data folder owned by another account is refused; its files are
   written owner-only; an empty or relative `XDG_DATA_HOME` or `APPDATA` is ignored.
6. Every data source the answers depend on — the atlas, the zone database, the zone boundaries,
   the star catalogue, the outlines of the areas the app reads by coordinates for historical
   clocks, and the list of the places whose zone is settled by a named source rather than by the
   boundaries alone — is checked against a recorded hash. The atlas has been rebuilt from
   downloads over HTTPS, each one's SHA-256 recorded in the atlas, not checked against one known
   beforehand. Each place takes the zone the boundaries give its
   coordinates, except where that list or an area rule says otherwise, each with its source;
   where the sources leave a place's offset unsettled, a Standard-time cast is refused and names
   both clocks.

**The build**

7. Each build machine installs its own hashed lock and nothing else (`pip install --require-hashes`
   of `requirements-build-windows.lock` or `requirements-build-macos.lock`, PyInstaller and its
   hooks included), and every version a lock shares with the set the tests run on is the same;
   only the build tools pip fetches to compile the three packages with no wheel for this Python
   are outside the locks. Only the job that publishes holds a write token, and its one other step
   is the download of the zips, an action pinned to its commit; checkout does not keep the token.
   Exactly one job creates the release.
8. The draft carries both platform zips and `SHA256SUMS`, the release job's SHA-256 of each, and
   `sha256sum -c SHA256SUMS` (`shasum -a 256 -c SHA256SUMS` on macOS), run where the two zips
   are downloaded from the draft, prints `OK` for both. The macOS zip keeps the bundle's symlinks.
   A rebuild cannot silently replace the files of a release already made.
9. `tests.yml` reuses no environment that one branch's run can change for another's, and declares
   its token permissions.

**The instruments**

10. Each guard and scanner has failed on a planted defect since the last release: the skip guard,
    the private-path and marker checks, the page-text and escaping tests, and every tool in `tools/`.
    A tool that reports clean on a crash, on empty input or on a mistyped filter is a failing tool.
11. `zizmor`, `actionlint`, `pip-audit` and `bandit` have run on the commit being released, and
    every item they report has been read and judged.

3. **Publish the drop and release.** The drop is a single commit with no parent whose tree is the
   tested commit's less the paths in `tools/private-paths.txt`, as `origin/main` lists them and
   as the tested commit does. It is cut in a throwaway clone of the development repository,
   never in a working checkout, and published with its tag in one push: the public
   repository's new `main` and the tag `vX.Y.Z` naming it land together or not at all.

   **The public rulesets.** Four rulesets guard the public repository. `Prot`, on the default
   branch, refuses its deletion, any update, any non-fast-forward push and any change not made by
   pull request. A branch ruleset on every other branch refuses their creation, update and
   deletion. `Version Ruleset`, on tags matching `v*`, refuses their update and deletion, so a
   release tag names its commit for good. A tag ruleset on every other tag refuses their
   creation, update and deletion. A drop replaces `main` and cannot come by pull request, so set
   `Prot`'s enforcement to *Disabled* (the public repository's Settings → Rules → Rulesets) just
   before the block's push (before the block, run as a script), and back to *Active* once the
   block has read the push back (after it, run as a script); the block marks both places, and
   the hook still brakes in the meantime. The other three stay active all the time: the release
   tag is a new `v*` tag, which none of them refuses. The step ends by reading all four back.

   **The push's token.** The push needs write access to the public repository's contents and
   workflows (the drop carries the release workflow), and no administration: the rulesets are
   set by hand in the web pages.

   **The published name.** The commit and the tag carry a name as well as an address, and both
   are public for good. The name is the owner's choice, not whatever the machine supplies (an
   account's login or full name). The address is your GitHub `noreply` address
   (`<id>+<login>@users.noreply.github.com`, shown in your account's e-mail settings), never a
   private one. Once the owner has chosen the name, set both once, for every clone:

   ```bash
   git config --global zij.dropName "<the chosen name>"
   git config --global zij.dropEmail "<your GitHub noreply address>"
   ```

   While either is unset, step 3 refuses to cut a drop, and the hook refuses any drop whose
   author, committer or tagger is not exactly that name with exactly that address; it also
   refuses an address that is not a GitHub `noreply` one.

   **The suite's environment.** Run step 3 with the suite's Python exported as `ZIJ_PYTHON`:
   the interpreter of the environment that has the dev pins (`requirements-dev.txt`). The
   throwaway clone has no environment of its own, so the release gate (which flags a missing
   one) and the clean-clone run below both take the suite's Python from that variable.

   Run it in bash, line by line, from your development checkout, with the texts present.
   `<the suite's python>` is that interpreter's path; `<tested commit>` is the commit you tested
   in step 1, which must be on `origin/main`; `X.Y.Z` is the version, the tag without its `v`.
   Each line that checks something says what it prints when all is well; stop at any other
   answer. Each such line also ends in `|| exit 1`, so a check that fails ends the shell it runs
   in, line by line or as a script. Run as a script, run it with `bash -e`, which stops at any
   other line that fails as well. Run line by line, start `bash` first and give it the block, so
   that a stop ends that `bash` and returns you to your own shell. The lines that make the
   clones and enter the first end in `|| exit 1` too, so a run that cannot make its clone stops
   before it changes anything in your checkout.

   ```bash
   export ZIJ_PYTHON="<the suite's python>"
   "$ZIJ_PYTHON" -c 'import pytest, xdist, fontTools, brotli' && echo "suite python" || exit 1   # prints: suite python
   name=$(git config --global --get zij.dropName) && echo "$name" || exit 1   # prints: the chosen name
   email=$(git config --global --get zij.dropEmail) && echo "$email" || exit 1   # prints: your GitHub noreply address
   [ "$email" = "$(gh api user --jq '"\(.id)+\(.login)@users.noreply.github.com"')" ] && echo "signed-in account" || exit 1   # prints: signed-in account
   git fetch origin
   tested=$(git rev-parse --verify '<tested commit>^{commit}')
   git merge-base --is-ancestor "$tested" origin/main && echo "on main" || exit 1   # prints: on main
   (git show "$tested:tools/git-hooks/pre-push" | grep -q ZIJ_HOOK_FROM_MAIN && echo "hook defers to main") || exit 1   # prints: hook defers to main
   version=X.Y.Z
   work=$(mktemp -d) || exit 1
   git clone -q --no-checkout "$(git remote get-url origin)" "$work/drop" || exit 1
   cd "$work/drop" || exit 1
   git checkout -q --detach "$tested"
   git config core.hooksPath tools/git-hooks
   git remote add public https://github.com/dar-al-hikma/Zij.git
   (git ls-remote --exit-code public "refs/tags/v$version" > /dev/null; [ $? -eq 2 ] && echo "tag is new") || exit 1   # prints: tag is new
   git show origin/main:tools/git-hooks/pre-push > "$work/pre-push" || exit 1
   git show origin/main:tools/private-paths.txt > "$work/main.txt" && git show "$tested:tools/private-paths.txt" > "$work/tested.txt" || exit 1
   bash "$work/pre-push" --private-paths "$work/main.txt" "$work/tested.txt" > "$work/private.nul" || exit 1   # prints nothing
   git --literal-pathspecs rm -r -q --cached --ignore-unmatch --pathspec-file-nul --pathspec-from-file="$work/private.nul" || exit 1
   git diff --cached --stat HEAD                  # only deletions, of the listed paths
   git diff --cached --name-status --diff-filter=d --exit-code HEAD || exit 1   # prints nothing
   drop=$(git -c user.name="${name:?is unset: the owner chooses the published name; set it once with git config --global zij.dropName <the chosen name>}" -c user.email="${email:?is unset: set your GitHub noreply address once with git config --global zij.dropEmail <your GitHub noreply address>}" -c i18n.commitEncoding=UTF-8 commit-tree -m "Zīj (زِيج) v$version" "$(git write-tree)")
   git reset -q                                   # the index back to the tested commit: a clean tree
   git -c user.name="$name" -c user.email="$email" -c tag.gpgSign=false tag -a "v$version" -m "Zīj (زِيج) v$version" "${drop:?}"
   check=$(mktemp -d) || exit 1
   git clone -q --no-checkout . "$check/zij" || exit 1
   git -C "$check/zij" checkout -q --detach "$drop"
   (cd "$check/zij" && CORPUS_DIR=/nonexistent "$ZIJ_PYTHON" -m pytest tests -q -n auto && echo "suite passed") || exit 1   # prints: suite passed
   # now set Prot to Disabled
   ZIJ_PUBLIC_DROP=1 git push --atomic public "+${drop:?}:refs/heads/main" "refs/tags/v$version" || exit 1
   [ "$(git ls-remote public refs/heads/main | cut -f 1)" = "$drop" ] && [ "$(git ls-remote public "refs/tags/v$version^{}" | cut -f 1)" = "$drop" ] && echo "main and tag name the drop" || exit 1   # prints: main and tag name the drop
   # now set Prot back to Active
   cd - && rm -rf "$work" "$check"
   ```

   The clone gives the drop nothing but what the tested commit holds: no untracked file, no
   uncommitted edit, nothing from another branch. The `tag is new` line stops the block when
   `vX.Y.Z` is already on the public repository: that version has been published, whole or in
   part, and is not cut again (see below). The two lists are read by `origin/main`'s copy of the
   hook, the reader its own checks use, and Git takes each entry as the literal path it is; a
   line that is not a plain path from the repository's top stops the block, naming the line,
   before anything is cut. The two `diff` lines run before
   anything is pushed. The suite runs in a clean clone of the drop, without the texts, as a
   stranger would, in a directory `mktemp` made for it. The commit, the tag and their messages carry the
   published name, the published address and the one line `Zīj (زِيج) vX.Y.Z`, nothing more: a
   message written here is public for good. With the name or the address unset its line stops
   the block, and the `commit-tree` line refuses too, so no drop is cut and nothing is pushed.
   The `gh api` line checks the address you set against the account you are signed in with,
   since the hook can check only that it is a `noreply` address and that every line carries
   it. The `hook defers to main` line checks that the tested commit's hook runs `origin/main`'s copy;
   a commit older than that switch would be judged by its own, older checks, so release a
   later commit instead.

   If the hook refuses because local `main` and `origin/main` differ, `main` moved while the
   release was being cut. `git fetch`, which that line suggests, does not cure it: start step 3
   again from its first line, so that the block makes a fresh clone. The tested commit can stay
   the same.

   **The push** carries both refs with `--atomic`, so GitHub takes both or neither; if GitHub
   did not take atomic pushes, Git would refuse before sending anything. The `+` forces `main`
   alone; the tag is new and is never forced. The line after it reads the public repository back
   and stops unless `main` and the tag, peeled, both name the drop; only then is `Prot` set back
   to *Active*.

   **If the push is refused**, by the hook, by GitHub or by Git, nothing changed on the public
   repository: set `Prot` back to *Active*, read the rulesets back (below), find the cause in
   what was printed, and run step 3 again from its first line.

   **If a ruleset was left disabled**, set it to *Active* and read all four back; until then
   GitHub refuses nothing that ruleset guards, and only the hook brakes, in a clone that has it.

   **If the read-back line stops the block**, read the public refs again (`git ls-remote
   public`): if `main` and the tag, peeled, both name the drop, the release is whole; set `Prot`
   back to *Active*. If they do not, treat it as below.

   **If a wrong tag or `main` reached the public repository**, past the brake (from a clone
   without the hook, with `--no-verify`, through GitHub's pages) or as the read-back shows,
   push nothing more: the hook refuses every deletion and every move of a tag. Undo
   it through GitHub's API, setting each ruleset that guards the ref to *Disabled* for the
   change alone. A wrong `main`: disable `Prot`, then force `main` back to the commit the last
   good release's tag names (`gh api -X PATCH repos/dar-al-hikma/Zij/git/refs/heads/main -f
   sha=<that commit> -F force=true`). A wrong `v` tag: disable `Version Ruleset`, then delete the
   tag (`gh api -X DELETE repos/dar-al-hikma/Zij/git/refs/tags/vX.Y.Z`) and any release drafted
   from it (item 6). A stray branch or other tag: disable the ruleset on other branches or other
   tags, and delete it the same way. Set each back to *Active* and read all four back. The
   version of a deleted tag is never used again: the fix is released under the next one. What
   was pushed was public while it stood: GitHub may go on showing a commit by its hash, and
   pull-request refs keep the commits they carried, which the owner cannot delete; only GitHub
   Support can remove those.

   The one `ZIJ_PUBLIC_DROP=1` prefix is the deliberate bypass of the pre-push hook. It is on the
   only push in the whole routine that should carry it; if you find yourself adding it to
   another, stop and work out what is being published.

   The hook checks the drop itself, and refuses it, with no override, unless every one of these
   holds:
   - the push only creates or replaces the public `main` and creates a release tag `vX.Y.Z`: it
     deletes nothing, writes no other branch or tag, and moves no tag already there;
   - the push carries both, together: the public `main` and exactly one new release tag, which,
     peeled, names exactly the commit `main` is set to, the drop, with no parent; a tag of any
     other commit is refused, even one with the same tree, name and message;
   - every entry of both lists is one path from the repository's top: a line with a space at
     either end, a `#` after the path, a `:` or `/` first, a backslash, a quote, a control
     character or one outside ASCII, a glob character (`*`, `?`, `[`) or an empty, `.` or `..`
     part refuses the whole list, naming the line;
   - the checkout stands at a commit on `origin/main`, and the pushed tree is exactly that
     commit's tree less the paths on either list, `origin/main`'s `tools/private-paths.txt` and
     the tested commit's own (rebuilt in a temporary index, so an added or changed file is
     refused);
   - no file in the drop is a development-only path or an agent's notes (`CLAUDE.md`,
     `AGENTS.md`, `GEMINI.md` and the like, wherever it sits), compared without regard to case,
     and again with anything from a `#` or `?` on cut off;
   - no file but an empty one has exactly the bytes of a file the two lists take out of the
     tested commit, whatever it is named;
   - no path holds a character outside ASCII, where a letter of another alphabet can make one
     name look like another;
   - no file is binary except the known assets: the atlas, the app icons, Swiss Ephemeris
     `.se1` files directly under `ephe/` and TrueType or OpenType fonts directly under `fonts/`,
     each exactly the file whose SHA-256 the hook pins, so an honest change to one, a rebuilt
     atlas or a new icon, carries its new SHA-256 into the hook's `ASSET_PINS` in the same pull
     request; a WOFF or WOFF2 font is refused, since its tables are compressed and cannot be
     searched;
   - no file, binary ones included, and neither message carries a page marker of the private
     texts, in any volume or spacing, an estimated page (`p. seq.`) included, and in any of the
     known assets as UTF-16 text too; nor does a text file in a spelling that hides one: wrapped
     over a line, behind an HTML entity, a `\u` escape, a Markdown escape or an emphasis tag, in
     full-width or invisible characters, opening a line without its emphasis, or inside base64
     (a run of sixteen characters or more besides any padding, on one line or wrapped over lines
     of sixteen or more of them but the last, each line nothing but the run and its straight
     quotes), gzip or zlib. A marker inside any other packing is not seen, which is why the
     binary files are pinned;
   - the commit's message and the tag's are exactly `Zīj (زِيج) vX.Y.Z` and its newline, the tag
     annotated and named for the same version, and `engine.py`'s `APP_VERSION` is that version;
   - the commit's author and committer and the tag's tagger are exactly the name `zij.dropName`
     sets, which may not be this machine's login, and exactly the address `zij.dropEmail` sets,
     which must be a GitHub `noreply` address on one line;
   - the commit's header is exactly its tree, author and committer lines and the tag's exactly
     its object, type, name and tagger lines, none twice and nothing else: no signature and no
     encoding line, which the `-c` settings on the `commit-tree` and `tag -a` lines above keep
     your own settings from adding;
   - the push publishes one commit with no parent;
   - the clock passes: `origin/main`'s copy of `tools/state.py`, run as
     `--strict --release <the tested commit>`, finds the checkout standing at that commit and
     clean, the texts present and their checkout the corpus of record, a citation register that
     describes that commit, and no locator awaiting registration.

   The tag on the **public** repository is what builds: the workflow runs there on hosted
   Windows and macOS runners (free for a public repository; a private one would bill macOS at
   ten times the minute) and creates a **draft** release with the two zips and `SHA256SUMS`
   attached and no notes. Before either zip is handed on, each runner starts its download from
   the zip, reaches it, and stops it twice, by closing its window and by ending its launcher
   alone, and starts its server once more to type a place in the city search; a process left
   running, a server that never answers, a server that lets a session connect under another
   site's name pointed at the runner or will not let one connect under its own address, a window
   that never opens, a launcher that makes no window log (the sign that the download loaded its
   engine) or a city search that does not offer the place typed fails the build, and no release
   is drafted.
   A build started by hand runs the same check. Write the notes yourself,
   then publish the draft: a release note says what this download is and what is true only of
   this release, and links the README for the rest rather than repeating it. A push to `main`
   builds nothing — only a `v*` tag or a manual run does.

   Once the push is read back and `Prot` is *Active* again, end the step by reading all four
   rulesets back:

   ```bash
   gh api repos/dar-al-hikma/Zij/rulesets --jq '.[] | "\(.target) \(.name) \(.enforcement)"'   # prints: four lines, each ending in active
   ```

   Each line is one ruleset: what it guards, its name and its `enforcement`, the field to read.
   There are four lines, `branch Prot`, a second `branch` line, `tag Version Ruleset` and a
   second `tag` line, and all four must end in `active`; if one says `disabled`, set it to
   *Active* and read again.
4. **Version numbers.** Zīj's line begins at v1.0.0. A minor bump for new rules and wording, a
   major one when what the app computes on every chart changes. A released number is never
   reused, even if the release is later withdrawn: people downloaded it. A pushed tag is never
   moved, and is deleted only when it is wrong (step 3): if its build fails, run it again from
   its run page, or release the fix under the next number.
5. **The test suite** runs on the development repository, on the self-hosted runner. That
   repository carries its own active ruleset, so the pull-request flow there is enforcement, not
   convention: open the PR, wait for `pytest`, merge green.
6. **Withdrawing a release.** The release lives on the **public** repository, not on `origin`:
   `gh release delete vX.Y.Z --repo dar-al-hikma/Zij --yes` removes it and its downloads, and
   that is all a withdrawal can remove. The tag stays (the tag ruleset and the hook both refuse
   its deletion), so its commit stays readable, and that commit stays the public `main` until
   the next drop replaces it. Pull requests opened on the public repository keep the commits
   they carried, and the owner cannot delete them; GitHub may go on showing any commit by its
   hash; the build's run page stays. A released version number is never reused afterwards.

## The suite in CI

`tests.yml` runs the full suite on every PR and push to `main`: about three minutes on the
self-hosted runner, which is registered to the organisation, not to a repository (a second,
per-repository registration of the same machine duplicates the runner); about 33 on the hosted
fallback, started by hand when that machine is off; the stuck-job guard is 45. The `pytest` check is
defined by the pull request it gates: a pull request runs its own branch's copy of `tests.yml` and of
the suite, so a green check shows only that the branch's own workflow passed. What gates a merge is
the full suite run locally with the private texts present, where nothing may skip. The tests that
read the private texts skip in CI; they run locally. The suite enforces the difference itself (`tests/skip_guard.py`): with the texts
present nothing may skip, and without them a test may skip only through the guard's own check
that the texts are absent. Any other skip fails the run — a check that skips is not a check. A run that ends *cancelled* rather than *failed* hit the guard, not a test.
