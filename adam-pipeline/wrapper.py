import argparse
import json
import logging
import os
import shutil
import subprocess
import textwrap
from uuid import uuid4

logging.basicConfig(level=logging.INFO)
log = logging.getLogger()


def write_config(mount, args):
    
    # open path to write config file at
    path = "adam-preprocessing-%s.config" % (str(uuid4()))
    fp = open(path, 'w')

    # generate config
    config = textwrap.dedent('''# ADAM preprocessing pipeline configuration file; autogenerated, do not modify!
    num-nodes:
    master-ip:
    dbsnp: %s
    memory: %s
    run-local: true
    local-dir: %s
    ''' % (args.known_sites, args.memory, mount))

    # write config to file
    print >> fp, config

    # flush and close file
    fp.flush()
    fp.close()

    # return config file name
    return path


def call_pipeline(mount, args):
    
    # get uuid and make a work directory
    uuid = 'toil-adam-' + str(uuid4())
    work_dir = os.path.join(mount, uuid)
    if not os.path.isdir(work_dir):
        os.makedirs(work_dir)

    # write config file locally
    conf = write_config(mount, args)

    # set python path and build command
    os.environ['PYTHONPATH'] = '/opt/adam-pipeline/src'
    command = ['python', '-m', 'toil_scripts.adam_pipeline.adam_preprocessing',
               'run',
               os.path.join(mount, 'jobStore'),
               '--retryCount', '1',
               '--output-dir', mount,
               '--workDir', work_dir,
               '--config', conf,
               '--sample', args.sample]
    
    # run the command and clean up
    try:
        subprocess.check_call(command)
    finally:
        stat = os.stat(mount)
        subprocess.check_call(['chown', '-R', '{}:{}'.format(stat.st_uid, stat.st_gid), mount])
        shutil.rmtree(work_dir)


def main():
    """
    Please see the complete documentation located at:
    https://github.com/BD2KGenomics/cgl-docker-lib/tree/master/adam-pipeline
    or in the container at:
    /opt/adam-pipeline/README.md

    All samples and inputs must be reachable via Docker "-v" mount points and use
    the Destination path prefix.
    """
    # Define argument parser for
    parser = argparse.ArgumentParser(description=main.__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('--known-sites', required=True,
                        help='Absolute path to VCF file with known SNPs.')
    parser.add_argument('--sample', required=True,
                        help='Absolute path to input SAM/BAM file.')
    parser.add_argument('--memory', required=True,
                        help='Java formatted memory string for allocating memory for Spark.')
    args = parser.parse_args()

    # Get name of most recent running container (should be this one)
    name = subprocess.check_output(['docker', 'ps', '--format', '{{.Names}}']).split('\n')[0]

    # Get name of mounted volume
    blob = json.loads(subprocess.check_output(['docker', 'inspect', name]))
    mounts = blob[0]['Mounts']

    # Ensure docker.sock is mounted correctly
    sock_mount = [x['Source'] == x['Destination'] for x in mounts if 'docker.sock' in x['Source']]
    if len(sock_mount) != 1:
        raise IllegalArgumentException('Missing socket mount. Requires the following:'
                                       'docker run -v /var/run/docker.sock:/var/run/docker.sock')

    # Ensure formatting of command for 2 mount points
    if len(mounts) == 2:
        if not all(x['Source'] == x['Destination'] for x in mounts):
            raise IllegalArgumentException('Docker Src/Dst mount points, invoked with the -v argument,'
                                           'must be the same if only using one mount point aside from the '
                                           'docker socket.')
        work_mount = [x['Source'] for x in mounts if 'docker.sock' not in x['Source']]
    else:
        # Ensure only one mirror mount exists aside from docker.sock
        mirror_mounts = [x['Source'] for x in mounts if x['Source'] == x['Destination']]
        work_mount = [x for x in mirror_mounts if 'docker.sock' not in x]
        if len(work_mount) > 1:
            raise IllegalArgumentException('Too many mirror mount points provided, see documentation.')
        if len(work_mount) == 0:
            raise IllegalArgumentException('No required mirror mount point provided, see documentation.')

    # call the pipeline
    call_pipeline(work_mount[0], args)


class IllegalArgumentException(Exception):
    pass


if __name__ == '__main__':
    main()
