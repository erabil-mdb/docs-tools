import re
import logging
import pkg_resources
import os.path
from multiprocessing import cpu_count

logger = logging.getLogger(os.path.basename(__file__))

from giza.tools.strings import timestamp
from giza.tools.shell import command

#################### Config Resolution ####################

def is_parallel_sphinx(version):
    return version >= '1.2'

def get_tags(target, sconf):
    ret = set()

    ret.add(target)
    ret.add(target.split('-')[0])

    if target.startswith('html') or target.startswith('dirhtml'):
        ret.add('website')
    else:
        ret.add('print')

    if 'edition' in sconf:
        ret.add(sconf['edition'])

    return ' '.join([' '.join(['-t', i ])
                     for i in ret
                     if i is not None])

def get_sphinx_args(sconf, conf):
    o = []

    o.append(get_tags(sconf['builder'], sconf))
    o.append('-q')

    o.append('-b {0}'.format(sconf['builder']))

    if (is_parallel_sphinx(pkg_resources.get_distribution("sphinx").version) and
        'editions' not in sconf):
        o.append(' '.join( [ '-j', str(cpu_count() + 1) ]))

    o.append(' '.join( [ '-c', conf.paths.projectroot ] ))

    if 'language' in sconf:
        o.append("-D language='{0}'".format(sconf['language']))

    return ' '.join(o)

#################### Output Management ####################

def output_sphinx_stream(out, conf):
    out = [ o for o in out.split('\n') if o != '' ]

    full_path = os.path.join(conf.paths.projectroot, conf.paths.branch_output)

    regx = re.compile(r'(.*):[0-9]+: WARNING: duplicate object description of ".*", other instance in (.*)')

    printable = []
    for idx, l in enumerate(out):
        if is_msg_worthy(l) is not True:
            printable.append(None)
            continue

        f1 = regx.match(l)
        if f1 is not None:
            g = f1.groups()

            if g[1].endswith(g[0]):
                printable.append(None)
                continue

        l = path_normalization(l, full_path, conf)

        if l.startswith('InputError: [Errno 2] No such file or directory'):
            l = path_normalization(l.split(' ')[-1].strip()[1:-2], full_path, conf)
            printable[idx-1] += ' ' + l
            l = None

        printable.append(l)

    printable = list(set(printable))
    printable.sort()

    print_build_messages(printable)

def print_build_messages(messages):
    for l in ( l for l in messages if l is not None ):
        print(l)

def path_normalization(l, full_path, conf):
    if l.startswith(conf.paths.branch_output):
        l = l[len(conf.paths.branch_output)+1:]
    elif l.startswith(full_path):
        l = l[len(full_path)+1:]

    if l.startswith('source'):
        l = os.path.sep.join(['source', l.split(os.path.sep, 1)[1]])

    return l

def is_msg_worthy(l):
    if l.startswith('WARNING: unknown mimetype'):
        return False
    elif len(l) == 0:
        return False
    elif l.startswith('WARNING: search index'):
        return False
    elif l.endswith('source/reference/sharding-commands.txt'):
        return False
    elif l.endswith('Duplicate ID: "cmdoption-h".'):
        return False
    elif l.endswith('should look like "-opt args", "--opt args" or "/opt args"'):
        return False
    else:
        return True

#################### Builder Operation ####################

def run_sphinx(builder, sconf, conf):
    dirpath = os.path.join(conf.paths.branch_output, builder)
    if not os.path.exists(dirpath):
        os.makedirs(dirpath)
        logger.info('created directories "{1}" for sphinx builder {0}'.format(builder, dirpath))

    logger.info('starting sphinx build {0} at {1}'.format(builder, timestamp()))

    cmd = 'sphinx-build {0} -d {1}/doctrees-{2} {3} {4}' # per-builder-doctreea

    sphinx_cmd = cmd.format(get_sphinx_args(sconf, conf),
                            os.path.join(conf.paths.projectroot, conf.paths.branch_output),
                            builder,
                            os.path.join(conf.paths.projectroot, conf.paths.branch_source),
                            os.path.join(conf.paths.projectroot, conf.paths.branch_output, builder))

    out = command(sphinx_cmd, capture=True, ignore=True)
    # out = sphinx_native_worker(sphinx_cmd)
    logger.info('completed sphinx build {0} at {1}'.format(builder, timestamp()))

    output = '\n'.join([out.err, out.out])

    if out.return_code == 0:
        logger.info('successfully completed {0} sphinx build at {1}!'.format(builder, timestamp()))
        logger.critical('finalizing builds is not implemented')
        # if finalize_fun is not None:
        #     finalize_fun(builder, sconf, conf)
        #     logger.info('finalized sphinx {0} build at {1}'.format(builder, timestamp()))
        output_sphinx_stream(output, conf)
    else:
        logger.warning('the sphinx build {0} was not successful. not running finalize steps'.format(builder))
        output_sphinx_stream(output, conf)

    return output

def sphinx_tasks(sconf, conf, app):
    task = app.add('task')
    task.job = run_sphinx
    task.conf = conf
    task.args = [sconf['builder'], sconf, conf]
    task.description = 'building {0} with sphinx'.format(sconf['builder'])
