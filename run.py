# Houses basic logic for running the assignment grading.

import mimetypes
import argparse
import os
import re
from docker import Client
import gzip
from utils import make_gzip

def grade(args, cli):
    cleanup = []

    if not os.path.isdir(args.folder):
        print("Must provide a valid folder of assignments")
        return

    if args.extra is not None and not os.path.isfile(args.extra):
        print("Extra argument must be a valid file.")
        return
    elif args.extra is not None:
        # if it's not a gzipped tarball, make it one
        if os.path.isdir(args.extra) or mimetypes.guess_type(args.extra)[1] != \
            'gzip':
            print("Creating temporary gzip file for extra")
            args.extra = make_gzip(args.extra)
            cleanup.append(args.extra)

    # Scrape the top level files and folders
    (dirpath, dirnames, filenames) = next(os.walk(args.folder))
    dirnames = map(lambda x: os.path.join(dirpath, x), dirnames)
    filenames = map(lambda x: os.path.join(dirpath, x), filenames)

    # Create a container for a file/folder
    for folder in dirnames:
        # cleanup name
        name = re.sub(r'_submit$', '', os.path.basename(folder))
        cleanup.append(make_gzip(folder, name))
        create_container(cli, dirpath, cleanup[-1], args.image, args.extra)

    # assumed gzips
    for filename in filenames:
        create_container(cli, dirpath, filename, 
                args.image, args.extra)

    print("Cleaning up temporary files")
    for f in cleanup:
        os.remove(f)

def create_container(cli, folder, file, image, extra=None):
    """
    Pass in a docker connection, a the folder source name (ie HW8), a filename
    (can be a folder name, supports stripping _submit), and a imagefile name.
    """
    user = os.path.basename(file)
    # Strip extension or filetype, if any
    user = re.sub(r'(_submit|\.[^\/]+)$', '', user)
    
    print("{0}:".format(user))
    # Get the name from the target folder (ie HW8) + username
    name = "{0}_{1}".format(os.path.basename(folder), user)

    # Check if container exists
    containers = cli.containers(all=True)
    for c in containers:
        for container_name in c['Names']:
            if container_name[1:] == name: # prefixed with /?
                # Try not to clobber images that aren't this
                if c['Image'] != image:
                    print(("  Container already exists for \"{0}\" and it "
                      + "doesn't appear to match the provided image. Skipping "
                      + "assignment").format(name))
                    return

                print("  Removing old container")
                try:
                    cli.remove_container(c['Id'], force=True)
                except Exception as e:
                    print("  Failed to remove. {0}.\n  Skipping assignment."\
                        .format(str(e)))
                    return
                break

    hostconf = cli.create_host_config(mem_limit='64m')
    # Create container
    id = cli.create_container(image=image, host_config=hostconf, 
            network_disabled=True, name=name, detach=True, tty=True,
            command="/bin/bash")
    # Copy provided file
    print("  Extracting assignment")
    with gzip.open(os.path.abspath(file)) as g:
        cli.put_archive(container=id, path="/home/", data=g.read())

    # Copy extra file
    if extra is not None:
        print("  Extracting extra file")
        with gzip.open(os.path.abspath(extra)) as g:
            cli.put_archive(container=id, path="/home/", data=g.read())
    print("  Container created")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Grade assignments.')
    parser.add_argument('folder', metavar='folder', 
                       help='Folder of tarballs or assignment folders.')
    parser.add_argument('--image', default='5201', help='Docker image for assignments.')
    #NOTE: This could be done with volumes. Is that better..?
    parser.add_argument('--extra', default=None, help='Extra files to copy into container (tarball).')

    args = parser.parse_args()

    # Connect up with docker
    cli = Client(base_url='unix://var/run/docker.sock')

    grade(args, cli)
