'''
Created on 2014-02-12

A module to load station data from the Water Survey of Canada and associate the data with river basins;
the data is stored in human-readable text files and tables. 

@author: Andre R. Erler, GPL v3
'''

# external imports
import numpy as np
import os, functools
from copy import deepcopy
# internal imports
from datasets.common import selectElements, data_root
from geodata.netcdf import DatasetNetCDF
from geodata.misc import FileError, isNumber, ArgumentError
from utils import nanfunctions as nf
from geodata.gdal import Shape, ShapeSet
from geodata.station import StationDataset, Variable, Axis
# from geodata.utils import DatasetError
from collections import OrderedDict

## WSC (Water Survey Canada) Meta-data

dataset_name = 'WSC'
root_folder = '{:s}/{:s}/'.format(data_root,dataset_name) # the dataset root folder

# variable attributes and name
variable_attributes = dict(runoff = dict(name='runoff', units='kg/m^2/s', atts=dict(long_name='Average Runoff Rate')), # average flow rate
                           roff_std = dict(name='roff_std', units='kg/m^2/s', atts=dict(long_name='Runoff Rate Variability')), # flow rate variability
                           roff_sem = dict(name='roff_sem', units='kg/m^2/s', atts=dict(long_name='Runoff Rate Error')), # flow rate error
                           roff_max = dict(name='roff_max', units='kg/m^2/s', atts=dict(long_name='Maximum Runoff Rate')), # maximum flow rate
                           roff_min = dict(name='roff_min', units='kg/m^2/s', atts=dict(long_name='Minimum Runoff Rate')), # minimum flow rate
                           discharge = dict(name='discharge', units='kg/s', fileunits='m^3/s', scalefactor=1000., atts=dict(long_name='Average Flow Rate')), # average flow rate
                           discstd = dict(name='StdDisc', units='kg/s', fileunits='m^3/s', scalefactor=1000., atts=dict(long_name='Flow Rate Variability')), # flow rate variability
                           discsem = dict(name='SEMDisc', units='kg/s', fileunits='m^3/s', scalefactor=1000., atts=dict(long_name='Flow Rate Error')), # flow rate error
                           discmax = dict(name='MaxDisc', units='kg/s', fileunits='m^3/s', scalefactor=1000., atts=dict(long_name='Maximum Flow Rate')), # maximum flow rate
                           discmin = dict(name='MinDisc', units='kg/s', fileunits='m^3/s', scalefactor=1000., atts=dict(long_name='Minimum Flow Rate')), # minimum flow rate
                           level = dict(name='level', units='m', atts=dict(long_name='Water Level'))) # water level
# list of variables to load
variable_list = variable_attributes.keys() # also includes coordinate fields    
# alternate WSC runoff variable names (for use with aggregation mode)
agg_varatts = dict()
for varname,varatts in variable_attributes.iteritems():
  tmpatts = varatts.copy() 
  if tmpatts['units'] == 'kg/m^2/s': tmpatts['name'] = 'runoff'  # always name 'runoff'
  elif tmpatts['units'] == 'kg/s': tmpatts['name'] = 'discharge'  # always name 'discharge'
  agg_varatts[varname] = tmpatts    

# custom exception for missing gage station data
class GageStationError(FileError):
  ''' Exception indicating that gage station data is missing '''
  pass

  
# container class for stations and area files
class Basin(Shape):
  ''' a Shape class for river basins with associated gage station information '''
  def __init__(self, name=None, long_name=None, shapefile=None, folder=None, load=False, ldebug=False,
               subbasins=None, rivers=None, stations=None):
    ''' save meta information; should be initialized from a BasinInfo instance '''
    super(Basin,self).__init__(name=name, long_name=long_name, shapefile=shapefile, folder=folder, 
                               load=load, ldebug=ldebug)
    # figure out if we are the outline/main basin
    name = self.name
    if 'Whole{:s}'.format(self.name) in subbasins: name = 'Whole{:s}'.format(self.name)
    assert name in subbasins, (name,subbasins)
    # add gage station from dict (based on name)
    if isinstance(subbasins,dict) and name in subbasins and subbasins[name]:
      maingage = subbasins[name]
      if isinstance(station, (list,tuple)): maingage = '{}_{}'.format(*maingage)        
    elif rivers and stations and name[:5] == 'Whole':
      maingage = '{}_{}'.format(rivers[0],stations[rivers[0]][0]) # first station of first river (from outflow)
    else: maingage = None # no gage station defined
    # initialize gage station
    self.maingage = None if maingage is None else GageStation(basin=name, name=maingage, folder=folder) # just name, for now
    
  def getMainGage(self, varlist=None, varatts=None, aggregation=None, mode='climatology', 
                  filetype='monthly'):
    ''' return a dataset with data from the main gaging station '''
    if self.maingage is not None:
      station = loadGageStation(basin=self.name, varlist=varlist, varatts=varatts, 
                                aggregation=aggregation, mode=mode, filetype=filetype)
    else: station = None 
    return station

# a container class for basin meta data
class BasinSet(ShapeSet,Basin): 
  ''' a container class for basins with associated subbasins '''
  _ShapeClass = Basin # the class that is used to initialize the shape collection
  
  def __init__(self, name=None, long_name=None, rivers=None, stations=None, subbasins=None, data_source=None, folder=None):
    ''' some common operations and inferences '''
    # call parent constructor 
    if folder is None: folder = '{:s}/Basins/{:s}/'.format(root_folder,long_name)
    shapefiles = subbasins.keys() if isinstance(subbasins, dict) else subbasins
    super(BasinSet,self).__init__(name=name, long_name=long_name, shapefiles=shapefiles, 
                                  data_source=data_source, folder=folder, # ShapeSet arguments
                                  rivers=rivers, stations=stations, subbasins=subbasins) 
                                  # N.B.: addition arguments for Basin constructor
    # add basin specific stuff
    self.subbasins = self.shapes # alias
    # self.maingage = stations[rivers[0]][0] if stations else None # should already be set by Basin init
    assert self.maingage is not None or not stations, stations # internal check
    self.rivers = rivers
    # add list of gage stations
    self.river_stations = OrderedDict(); self.stations = OrderedDict()
    for river,station_list in stations.items():
      self.river_stations = [GageStation(name=station, river=river, folder=folder) 
                             for station in station_list]
      for station in self.river_stations: self.stations[station.name] = station     
        
      
# a class to hold meta data of gaging stations
class GageStation(object):
  ''' a class that provides access to station meta data and gage data '''
  meta_ext = '_Metadata.csv'
  meta_file = None
  monthly_ext = '_Monthly.csv'
  monthly_file = None
  
  def __init__(self, basin=None, river=None, name=None, folder=None):
    ''' initialize gage station based on various input data '''
    if name is None: raise ArgumentError()
    if folder is None: folder = '{:s}/Basins/{:s}/'.format(root_folder,basin)
    if not os.path.isdir(folder): IOError(folder)
    if river is not None and river not in name: name = '{:s}_{:s}'.format(river,name)
    if not os.path.isdir(folder): IOError(folder)
    self.folder = folder # usually basin folder
    self.name = name # or prefix...
    if os.path.isfile('{:s}/{:s}'.format(folder,name + self.meta_ext)):
      self.meta_file = name + self.meta_ext
    if os.path.isfile('{:s}/{:s}'.format(folder,name + self.monthly_ext)):
      self.meta_file = name + self.monthly_ext
    
    
## Functions that handle access to ASCII files
def loadGageStation(basin=None, station=None, varlist=None, varatts=None, mode='climatology', 
                    aggregation=None, filetype='monthly', folder=None, filename=None,
                    basins=None, basin_list=None):
  ''' Function to load hydrograph climatologies for a given basin '''
  ## resolve input
  # resolve basin
  if isinstance(basin,basestring) and basin in basins: 
    basin = basin_list[basin]
  # determine basin meta data
  if isinstance(basin,BasinInfo):
    folder = basin.folder if folder is None else folder
    basin_name = basin.name
    # figure out station
    if station is None: station = basin.maingage      
    if not isinstance(station,basestring): raise TypeError(station)
    if station in basin.stationfiles: filename = basin.stationfiles[station]
    elif filename is None: # only a problem if there is no file to open
      raise GageStationError('Unknown station: {}'.format(station))
  # test folder and filename
  if isinstance(folder,basestring) and isinstance(filename,basestring):
    os.path.exists('{}/{}'.format(folder,filename))
  else: raise TypeError('Specify either basin & station or folder & filename.')
    
  # variable attributes
  if varlist is None: varlist = variable_list
  elif not isinstance(varlist,(list,tuple)): raise TypeError  
  varlist = list(varlist) # make copy of varlist to avoid interference
  if varatts is None: 
    if aggregation is None: varatts = deepcopy(variable_attributes) # because of nested dicts
    else: varatts = deepcopy(agg_varatts) # because of nested dicts
  elif not isinstance(varatts,dict): raise TypeError
  
  ## read csv data
  filepath = '{}/{}'.format(folder,filename)
  data = np.genfromtxt(filepath, dtype=np.float32, delimiter=',', skip_header=1, filling_values=np.nan,  
                       usecols=np.arange(4,28,2), usemask=True, loose=True, invalid_raise=True)
  # for some reason every value if followed by an extra comma...
  data = np.ma.masked_less(data, 10) # remove some invalid values
  data *= 1000. # m^3 == 1000 kg (water)
  ## load meta data
  # open namelist file for reading  
  filepath = '{}/{}'.format(folder,filename.replace('Monthly', 'Metadata')) 
  # parse file and load data into a dictionary
  with open(filepath, mode='r') as filehandle:
    lines = filehandle.readlines()
    assert len(lines) == 2, lines
    keys = lines[0].split(',')
    values = lines[1].split(',')
  assert len(keys) == len(values)
  # add some additional attributes
  metadata = {key:value for key,value in zip(keys,values)}
  metadata['long_name'] = metadata['Station Name']
  metadata['ID'] = metadata['Station Number']
  metadata['shape_name'] = basin_name
  metadata['shp_area'] = float(metadata['Drainage Area']) * 1e6 # km^2 == 1e6 m^2
  # create dataset for station
  dataset = StationDataset(name='WSC', title=metadata['Station Name'], varlist=[], atts=metadata,) 
  if mode == 'climatology': 
    # make common time axis for climatology
    te = 12 # length of time axis: 12 month
    climAxis = Axis(name='time', units='month', length=12, coord=np.arange(1,te+1,1)) # monthly climatology
    dataset.addAxis(climAxis, copy=False)
    # extract variables (min/max/mean are separate variables)
    # N.B.: this is mainly for backwards compatibility
    doa = data / metadata['shp_area']  
    if aggregation is None or aggregation.lower() == 'mean':
      # load mean discharge
      tmpdata = nf.nanmean(data, axis=0)
      tmpvar = Variable(axes=[climAxis], data=tmpdata, atts=varatts['discharge'])
      dataset.addVariable(tmpvar, copy=False)
      # load mean runoff
      tmpdata = nf.nanmean(doa, axis=0)
      tmpvar = Variable(axes=[climAxis], data=tmpdata, atts=varatts['runoff'])
      dataset.addVariable(tmpvar, copy=False)
    if aggregation is None or aggregation.lower() == 'std':
      # load  discharge standard deviation
      tmpdata = nf.nanstd(data, axis=0, ddof=1) # very few values means large uncertainty!
      tmpvar = Variable(axes=[climAxis], data=tmpdata, atts=varatts['discstd'])
      dataset.addVariable(tmpvar, copy=False)
      # load  runoff standard deviation
      tmpdata = nf.nanstd(doa, axis=0, ddof=1)
      tmpvar = Variable(axes=[climAxis], data=tmpdata, atts=varatts['roff_std'])
      dataset.addVariable(tmpvar, copy=False)
    if aggregation is None or aggregation.lower() == 'sem':
      # load  discharge standard deviation
      tmpdata = nf.nansem(data, axis=0, ddof=1) # very few values means large uncertainty!
      tmpvar = Variable(axes=[climAxis], data=tmpdata, atts=varatts['discsem'])
      dataset.addVariable(tmpvar, copy=False)
      # load  runoff standard deviation
      tmpdata = nf.nansem(doa, axis=0, ddof=1)
      tmpvar = Variable(axes=[climAxis], data=tmpdata, atts=varatts['roff_sem'])
      dataset.addVariable(tmpvar, copy=False)
    if aggregation is None or aggregation.lower() == 'max':
      # load maximum discharge
      tmpdata = nf.nanmax(data, axis=0)
      tmpvar = Variable(axes=[climAxis], data=tmpdata, atts=varatts['discmax'])
      dataset.addVariable(tmpvar, copy=False)
      # load maximum runoff
      tmpdata = nf.nanmax(doa, axis=0)
      tmpvar = Variable(axes=[climAxis], data=tmpdata, atts=varatts['roff_max'])
      dataset.addVariable(tmpvar, copy=False)
    if aggregation is None or aggregation.lower() == 'min':
      # load minimum discharge
      tmpdata = nf.nanmin(data, axis=0)
      tmpvar = Variable(axes=[climAxis], data=tmpdata, atts=varatts['discmin'])
      dataset.addVariable(tmpvar, copy=False)
      # load minimum runoff
      tmpdata = nf.nanmin(doa, axis=0)
      tmpvar = Variable(axes=[climAxis], data=tmpdata, atts=varatts['roff_min'])
      dataset.addVariable(tmpvar, copy=False)
  else: 
    raise NotImplementedError, "Time axis mode '{}' is not supported.".format(mode)
  # return station dataset
  return dataset   


## some helper functions to test conditions
# defined in module main to facilitate pickling
def test_encl(val, index,dataset,axis):
  ''' check if shape is fully enclosed by grid ''' 
  return dataset.shp_encl[index] == val  
def test_full(val, index,dataset,axis):
  ''' check if shape fully covers the grid ''' 
  return dataset.shp_full[index] == val
def test_empty(val, index,dataset,axis):
  ''' check if shape is outside of grid ''' 
  return dataset.shp_empty[index] == val 
def test_mina(val,index,dataset,axis):
  ''' check minimum area ''' 
  return dataset.shp_area[index] >= val
def test_maxa(val,index,dataset,axis):
  ''' check maximum area ''' 
  return dataset.shp_area[index] <= val
 
# apply tests to list
def apply_test_suite(tests, index, dataset, axis):
  ''' apply an entire test suite to '''
  # just call all individual tests for given index 
  return all(test(index,dataset,axis) for test in tests)

## select a set of common stations for an ensemble, based on certain conditions
def selectStations(datasets, shpaxis='shape', imaster=None, linplace=True, lall=False, **kwcond):
  ''' A wrapper for selectCoords that selects stations based on common criteria '''
  # pre-load NetCDF datasets
  for dataset in datasets: 
    if isinstance(dataset,DatasetNetCDF): dataset.load() 
  # list of possible constraints
  tests = [] # a list of tests to run on each station
  #loadlist =  (datasets[imaster],) if not lall and imaster is not None else datasets 
  # test definition
  for key,val in kwcond.iteritems():
    key = key.lower()
    if key[:4] == 'encl' or key[:4] == 'cont':
      val = bool(val)
      tests.append(functools.partial(test_encl, val))
    elif key == 'full':
      val = bool(val)
      tests.append(functools.partial(test_full, val))
    elif key[:4] == 'empt':
      val = bool(val)
      tests.append(functools.partial(test_empty, val))
    elif key == 'min_area':
      if not isNumber(val): raise TypeError
      val = val*1e6 # units in km^2  
      tests.append(functools.partial(test_mina, val))    
    elif key == 'max_area':
      if not isNumber(val): raise TypeError
      val = val*1e6 # units in km^2  
      tests.append(functools.partial(test_maxa, val))
    else:
      raise NotImplementedError, "Unknown condition/test: '{:s}'".format(key)
  # define test function (all tests must pass)
  if len(tests) > 0:
    testFct = functools.partial(apply_test_suite, tests)
  else: testFct = None
  # pass on call to generic function selectCoords
  datasets = selectElements(datasets=datasets, axis=shpaxis, testFct=testFct, imaster=imaster, linplace=linplace, lall=lall)
  # return sliced datasets
  return datasets


## abuse main block for testing
if __name__ == '__main__':
  
  from projects.WSC_basins import basin_list, basins, BasinSet
  # N.B.: importing BasinInfo through WSC_basins is necessary, otherwise some isinstance() calls fail
  
  basin_name = 'GRW'
    
  # verify basin info
  basin_set = basin_list[basin_name]
  print basin_set.long_name
  print basin_set.stations
  
  # load basins
  basin = basins[basin_name]
  print basin.long_name
  print basin
  assert basin.name == 'Whole'+basin_name
  
  # load station data
  station = basin.getMainGage(aggregation='std')
  print
  print station
  print
  assert station.ID == loadGageStation(basin=basin_name, basins=basins, basin_list=basin_list).ID
  print station.discharge.getArray()
  
  # print basins
  print
  for bsn in basins.iterkeys():
    print bsn