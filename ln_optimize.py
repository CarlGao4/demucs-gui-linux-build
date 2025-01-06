# Optimize the size of a folder by creating symbolic links to same files
import argparse
import concurrent.futures
import glob
import hashlib
import os
import sys
import tqdm

# assert sys.platform == "linux", "This script is only for Linux"

parser = argparse.ArgumentParser(description="Optimize the size of a folder by creating symbolic links to same files")
parser.add_argument("folder", help="Base folder to optimize")
parser.add_argument(
    "--method",
    help="Method to use for optimization",
    choices=["SHA1", "MD5", "SHA256", "SIZE", "CONTENT"],
    default="SHA256",
)
parser.add_argument("--skip-small", help="Skip files smaller than this size", type=int, default=1024)
parser.add_argument("--jobs", "-j", help="Number of parallel jobs", type=int, default=1)
parser.add_argument("--dry-run", help="Do not create links, only print what would be done", action="store_true")
parser.add_argument("-y", help="Do not ask for confirmation", action="store_true")
args = parser.parse_args()

if args.method == "CONTENT":
    print(
        "Using CONTENT method requires reading all files, which may cause out of memory error on large folders",
        file=sys.stderr,
    )

os.chdir(args.folder)
print("Moving to folder", args.folder)

sizes = {i: os.path.getsize(i) for i in glob.glob("**", recursive=True) if os.path.isfile(i) and not os.path.islink(i)}
print("Found", len(sizes), "files", file=sys.stderr)
sizes = {i: j for i, j in sizes.items() if j >= args.skip_small}
print(
    "Found %d files with total size %d bytes whose size is at least %d bytes"
    % (len(sizes), sum(sizes.values()), args.skip_small),
    file=sys.stderr,
)


def get_hash_size(file):
    return sizes[file]


def get_hash_content(file):
    with open(file, "rb") as f:
        return f.read()


def get_hash_sha1(file):
    with open(file, "rb") as f:
        hasher = hashlib.sha1()
        while data := f.read(65536):
            hasher.update(data)
        return hasher.digest()


def get_hash_md5(file):
    with open(file, "rb") as f:
        hasher = hashlib.md5()
        while data := f.read(65536):
            hasher.update(data)
        return hasher.digest()


def get_hash_sha256(file):
    with open(file, "rb") as f:
        hasher = hashlib.sha256()
        while data := f.read(65536):
            hasher.update(data)
        return hasher.digest()


match args.method:
    case "CONTENT":
        get_hash = get_hash_content
    case "SIZE":
        get_hash = get_hash_size
    case "SHA1":
        get_hash = get_hash_sha1
    case "MD5":
        get_hash = get_hash_md5
    case "SHA256":
        get_hash = get_hash_sha256

print("Getting hashes using method %s with %d parallel jobs" % (args.method, args.jobs), file=sys.stderr)
pool = concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs)
hashes = list(tqdm.tqdm(pool.map(lambda x: (x, get_hash(x)), sizes.keys()), total=len(sizes), file=sys.stderr))
pool.shutdown()

hash_maps = {}
for file, hash in hashes:
    hash_maps.setdefault(hash, []).append(file)

print("Found %d unique files from %d files" % (len(hash_maps), len(sizes)), file=sys.stderr)
if len(hash_maps) < len(sizes):
    print("Same files:", file=sys.stderr)
    for hash_value in list(hash_maps.keys()):
        hash_maps[hash_value].sort()
        files = hash_maps[hash_value]
        if len(files) > 1:
            if args.method != "CONTENT":
                print(
                    "Same files with hash %s:" % hash_value.hex() if isinstance(hash_value, bytes) else str(hash_value),
                    file=sys.stderr,
                )
            print(*files, sep="\n", end="\n\n", file=sys.stderr)
    print("-" * 40, file=sys.stderr)

if args.dry_run:
    print("Dry run, not creating links", file=sys.stderr)

reduced_size = 0

for files in hash_maps.values():
    if len(files) < 2:
        continue
    for file in files[1:]:
        if args.dry_run:
            print("Linking %s => %s (Dry run)" % (file, files[0]), file=sys.stderr)
        else:
            if not args.y:
                print("Link %s => %s ? [y/N]" % (file, files[0]), end="", file=sys.stderr)
                if input().lower() != "y":
                    continue
            print("Linking %s => %s ... " % (file, files[0]), end="", file=sys.stderr)
            try:
                os.unlink(file)
            except FileNotFoundError:
                pass
            except Exception as e:
                print("Error:", e, file=sys.stderr)
                continue
            try:
                os.symlink(files[0], file)
                print("success", file=sys.stderr)
            except Exception as e:
                print("Error:", e, file=sys.stderr)
                continue
        reduced_size += sizes[file]
print("Done", file=sys.stderr)
