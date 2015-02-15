'''
Created on 2011-02-28

utility functions, mostly for plotting, that are not called directly

@author: Andre R. Erler
'''

# external imports
import scipy
import numpy as np
import matplotlib as mpl
# internal imports
from geodata.misc import VariableError
from utils.signalsmooth import smooth # commonly used in conjunction with plotting...

# import matplotlib as mpl
# import matplotlib.pylab as pyl


# convenience function to load a stylesheet according to some rules 
def loadStyleSheet(stylesheet, lpresentation=False, lpublication=False):
  ''' convenience function to load a stylesheet according to some rules '''
  # select stylesheets
  if stylesheet is None: stylesheet = 'default'
  if isinstance(stylesheet,basestring):     
    if lpublication: stylesheet = (stylesheet,'publication')       
    elif lpresentation: stylesheet = (stylesheet,'presentation')
  # load stylesheets
  if isinstance(stylesheet,(list,tuple,basestring)): 
    mpl.pyplot.style.use(stylesheet)
  else: raise TypeError


# caculate error percentiles
def errorPercentile(percentile):
  ''' calculate multiple of standard deviations for error percentile (assuming normal distribution) '''
  return scipy.special.erfinv(percentile)*np.sqrt(2.)
def percentileError(multiple):
  ''' calculate the percentile included in multiple of standard deviations (assuming normal distribution) '''
  return scipy.special.erf(multiple/np.sqrt(2.))
# Source: https://docs.scipy.org/doc/scipy/reference/generated/scipy.special.erf.html
  

# method to check units and name, and return scaled plot value (primarily and internal helper function)
def getPlotValues(var, checkunits=None, checkname=None, lsmooth=False, lperi=False, laxis=False):
  ''' Helper function to check variable/axis, get (scaled) values for plot, and return appropriate units. '''
  # figure out units
  if var.plot is not None: 
    varname = var.plot.name 
    if checkname is not None and varname != checkname: # only check plotname! 
      raise VariableError, "Expected variable name '{}', found '{}'.".format(checkname,varname)
  else: varname = var.atts['name']
  val = var.getArray(unmask=True, copy=True) # the data to plot
  if var.plot is not None:
    if var.units != var.plot.units: 
      val = val *  var.plot.scalefactor
    varunits = var.plot.units
  else: 
    varunits = var.atts['units']
  if var.plot is not None and 'offset' in var.plot: val += var.plot.offset    
  if checkunits is not None and  varunits != checkunits: 
    raise VariableError, "Units for variable '{}': expected {}, found {}.".format(var.name,checkunits,varunits) 
  # some post-processing
  val = val.squeeze()
  if lsmooth: val = smooth(val)
  if lperi: 
    if laxis: 
      delta = np.diff(val)
      val = np.concatenate((val[:1]-delta[:1],val,val[-1:]+delta[-1:]))
    else: val = np.concatenate((val[-1:],val,val[:1]))
  # return values, units, name
  return val, varunits, varname     

  
# Log-axis ticks
def logTicks(ticks, base=None, power=0):
  ''' function to generate ticks for a given power of 10 based on a template '''
  if not isinstance(ticks, (list,tuple)): raise TypeError
  # translate base into power
  if base is not None: 
    if not isinstance(base,(int,np.number,float,np.inexact)): raise TypeError
    power = int(np.round(np.log(base)/np.log(10)))
  if not isinstance(power,(int,np.integer)): raise TypeError
  print power
  # generate ticks and apply template
  strtck = ['']*8
  for i in ticks:
    if not isinstance(i,(int,np.integer)) or i >= 8: raise ValueError
    idx = i-2
    if i in ticks: strtck[idx] = str(i)
    # adjust order of magnitude
    if power > 0: strtck[idx] += '0'*power
    elif power < 0: strtck[idx] = '0.' + '0'*(-1-power) + strtck[idx]
  # return ticks
  return strtck


# special version for wave numbers
# N, returns ['2','','4','','6','','','']
def nTicks(**kwargs): return logTicks([2,4,6],**kwargs)

# special version for pressure levelse 
# p, returns ['2','3','','5','','7','','']
def pTicks(**kwargs): return logTicks([2,3,5,7],**kwargs)

