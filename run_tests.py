import sys
import os
import subprocess
import getopt
from time import sleep

try:
  opts, args = getopt.getopt(sys.argv[1:], "M:c:v:r:")
except getopt.GetoptError as err:
  print str(err)
  sys.exit(2)

module = None
connector = 0
indev = None
resolutions = None

for o, a in opts:
  if o == '-M':
    module = a
  elif o == '-c':
    connector = a
  elif o == '-v':
    indev = a
  elif o == '-r':
    resolutions = [tuple(r.split('-', 2)) for r in a.split(',')]

if module == None:
  print 'specify module using -M'
  sys.exit(2)
if connector == 0:
  print 'specify connector using -c'
  sys.exit(2)
if indev == None:
  print 'specify video input device using -v'
  sys.exit(2)

if resolutions == None:
  try:
    conns = subprocess.check_output(['modetest', '-M', module, '-c'])
  except subprocess.CalledProcessError:
    print 'modetest failed to enumerate connectors for module ' + module
    sys.exit(3)

  resolutions = []
  modes = 1
  for l in conns.split('\n'):
    if modes < 0:
      modes += 1
    elif modes == 0:
      if 'props' in l:
        modes = 1
      else:
        res, hz = l.strip().split(' ')[0:2]
        print 'r',res,hz
        resolutions += [(res, hz)]
    elif l.startswith(str(connector) + '\t'):
      print 'gotmode'
      modes = -2

fails = 0
passes = 0

devnull = os.open(os.devnull, os.O_RDWR)
for r in resolutions:
  try:
    sys.stderr.write('Testing ' + r[0] + '-' + r[1] + '\n\t')
  except IndexError:
    print 'invalid resolution', '-'.join(r)
    sys.exit(3)
  
  # Emit test pattern
  sleep(1)
  try:
    p = subprocess.Popen(['modetest', '-M', module, '-s',
      str(connector) + ':' + r[0] + '-' + r[1]], stdin = subprocess.PIPE)
  except Exception as err:
    print 'failed to run modetest to emit test pattern: ' + str(err)

  # Wait for it to stabilize
  sleep(2)

  print '\tcapturing frame'
  # XXX: on R-Car H1/Lager, VIN occasinally fails to use up-to-date timings,
  # resulting in a cropped image; capture frame twice as a workaround
  for i in [1,2]:
    try:
      subprocess.check_call(['yavta', '-f', 'YUYV', '--capture=1', '-F', indev,
        '-s', r[0], '-d', '2000'], stdout=devnull)
    except subprocess.CalledProcessError:
      print 'yavta failed to capture frame from ', indev
      sys.exit(3)

  print '\tconverting frame'
  # Convert from raw format to something more easily digestable
  try:
    subprocess.check_call(['raw2rgbpnm', '-f', 'YUYV', '-s', r[0],
      'frame-000000.bin', 'frame-000000.pnm'], stdout=devnull)
  except subprocess.CalledProcessError:
    print 'raw2rgbpnm failed to convert captured frame to pnm'
    sys.exit(3)

  # scale to reference size
  try:
    subprocess.check_call(['convert', 'frame-000000.pnm', '-scale',
      '1024x768!', 'frame-1024x768.pnm'])
  except subprocess.CalledProcessError:
    print 'failed to scale captured frame to reference size'
    sys.exit(3)

  print '\tcomparing to reference:',
  try:
    mae = subprocess.check_output(['compare', '-metric', 'mae',
      'modetest-1024x768.pnm', 'frame-1024x768.pnm', '/dev/null'],
      stderr = subprocess.STDOUT)
  except subprocess.CalledProcessError as err:
    if err.returncode == 1:
      mae = err.output
    else:
      print 'failed to fuzzy compare captured frame with reference: ' + str(err)
      print mae
      sys.exit(3)

  mae = float(mae.split('(')[1].strip(')'))
  print 'mae',mae
  if mae < .01:
    print '\tPASS'
    passes += 1
  else:
    print '\tFAIL'
    fails += 1

  p.communicate('\n')
  if p.returncode != 0:
    print 'modetest returned with error'
    sys.exit(3)

print passes, 'passed,', fails, 'failed'
