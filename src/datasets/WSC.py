'''
Created on 2014-02-12

A module to load station data from the Water Survey of Canada and associate the data with river basins;
the data is stored in human-readable text files and tables. 

@author: Andre R. Erler, GPL v3
'''

# external imports
import numpy as np
import functools
import fileinput
from collections import OrderedDict
from copy import deepcopy
# internal imports
from datasets.common import selectElements, data_root
from geodata.netcdf import DatasetNetCDF
from geodata.misc import ParseError, isNumber
from geodata.gdal import NamedShape, ShapeInfo
from geodata.station import StationDataset, Variable, Axis
# from geodata.utils import DatasetError
from warnings import warn

## WSC (Water Survey Canada) Meta-data

dataset_name = 'WSC'
root_folder = data_root + dataset_name + '/'

# variable attributes and name
variable_attributes = dict(discharge = dict(name='discharge', units='kg/s', fileunits='m^3/s', scalefactor=1000., atts=dict(long_name='Average Flow Rate')), # average flow rate
                           discmax = dict(name='MaxDisc', units='kg/s', fileunits='m^3/s', scalefactor=1000., atts=dict(long_name='Maximum Flow Rate')), # maximum flow rate
                           discmin = dict(name='MinDisc', units='kg/s', fileunits='m^3/s', scalefactor=1000., atts=dict(long_name='Minimum Flow Rate')), # minimum flow rate
                           level = dict(name='level', units='m', atts=dict(long_name='Water Level'))) # water level
# list of variables to load
variable_list = variable_attributes.keys() # also includes coordinate fields    
          
  
# container class for stations and area files
class Basin(NamedShape):
  ''' Just a container for basin information and associated station data '''
  def __init__(self, basin=None, subbasin=None, folder=None, shapefile=None, basins_dict=None, load=False, ldebug=False):
    ''' save meta information; should be initialized from a BasinInfo instance '''
    super(Basin,self).__init__(area=basin,  subarea=subbasin, folder=folder, shapefile=shapefile, shapes_dict=basins_dict, load=load, ldebug=ldebug)
    self.maingage = basin.maingage if basin is not None else None 
    
  def getMainGage(self, varlist=None, varatts=None, mode='climatology', filetype='monthly'):
    ''' return a dataset with data from the main gaging station '''
    if self.maingage is not None:
      station = loadGageStation(basin=self.info, varlist=varlist, varatts=varatts, mode=mode, filetype=filetype)
    else: station = None 
    return station

# a container class for basin meta data
class BasinInfo(ShapeInfo): 
  ''' basin meta data '''
  def __init__(self, name=None, long_name=None, rivers=None, stations=None, subbasins=None, data_source=None, folder=None):
    ''' some common operations and inferences '''
    # call parent constructor 
    if folder is None: folder = root_folder + '/Basins/'
    super(BasinInfo,self).__init__(name=name, long_name=long_name, shapefiles=subbasins, shapetype='BSN', 
                                   data_source=data_source, folder=folder)
    # add basin specific stuff
    self.subbasins = subbasins
    self.maingage = stations[rivers[0]][0] if stations else None 
    self.stationfiles = dict()
    for river,station_list in stations.items():
      for station in station_list: 
        filename = '{0:s}_{1:}.dat'.format(river,station)
        if station in self.stationfiles: 
          warn('Duplicate station name: {}\n  {}\n  {}'.format(station,self.stationfiles[station],filename))
        else: self.stationfiles[station] = filename
      
# dictionary with basin meta data
basins_info = OrderedDict() # maintain order
# meta data for specific basins

basins_info['AY'] = BasinInfo(name='AY', long_name='Alaska and Yukon', rivers=[], data_source='WSC',
                               stations=dict(), subbasins=['WholeAY'])
basins_info['AO'] = BasinInfo(name='AO', long_name='Arctic Ocean', rivers=[], data_source='WSC',
                               stations=dict(), subbasins=['WholeAO'])
basins_info['ARB'] = BasinInfo(name='ARB', long_name='Athabasca River Basin', rivers=['Athabasca'], data_source='WSC',
                               stations=dict(Athabasca=['Embarras','McMurray']),
                               subbasins=['WholeARB','UpperARB','LowerARB'])
basins_info['CRB'] = BasinInfo(name='CRB', long_name='Columbia River Basin', rivers=['Columbia'], data_source='WSC',
                               stations=dict(), subbasins=['WholeCRB'])
basins_info['FRB'] = BasinInfo(name='FRB', long_name='Fraser River Basin', rivers=['Fraser'], data_source='WSC',
                               stations=dict(Fraser=['PortMann','Mission']),
                               subbasins=['WholeFRB','UpperFRB','LowerFRB'])
basins_info['GLB'] = BasinInfo(name='GLB', long_name='Great Lakes Basin', rivers=['Upper Saint Lawrence'], data_source='WSC',
                               stations=dict(), subbasins=['WholeGLB'])
basins_info['GSL'] = BasinInfo(name='GSL', long_name='Great Slave Lake', rivers=[], data_source='WSC',
                               stations=dict(), subbasins=['WholeGSL'])
basins_info['LS'] = BasinInfo(name='LS', long_name='Labrador Sea', rivers=[], data_source='WSC',
                               stations=dict(), subbasins=['WholeLS'])
basins_info['MKB'] = BasinInfo(name='MKB', long_name='MacKenzie Basin', rivers=['MacKenzie'], data_source='',
                               stations=dict(), subbasins=['WholeMKB'])
basins_info['MRB'] = BasinInfo(name='MRB', long_name='Missouri River Basin', rivers=['Missouri'], data_source='WSC',
                               stations=dict(), subbasins=['WholeMRB'])
basins_info['NRB'] = BasinInfo(name='NRB', long_name='Nelson River Basin', rivers=['Nelson'], data_source='WSC',
                               stations=dict(), subbasins=['WholeNRB'])
basins_info['NHB'] = BasinInfo(name='NHB', long_name='Northern Hudson Bay', rivers=[], data_source='WSC',
                               stations=dict(), subbasins=['WholeNHB'])
basins_info['NO'] = BasinInfo(name='NO', long_name='Northern Ontario', rivers=[], data_source='WSC',
                               stations=dict(), subbasins=['WholeNO'])
basins_info['PO'] = BasinInfo(name='PO', long_name='Pacific Ocean', rivers=[], data_source='WSC',
                               stations=dict(), subbasins=['WholePO'])
basins_info['PSB'] = BasinInfo(name='PSB', long_name='Pacific Seaboard', rivers=[], data_source='WSC',
                               stations=dict(), subbasins=['WholePSB','NorthernPSB','SouthernPSB'])
basins_info['SLR'] = BasinInfo(name='SLR', long_name='Saint Lawrence River', rivers=['Saint Lawrence'], data_source='WSC',
                               stations=dict(), subbasins=['WholeSLR'])

# N.B.: all shapefiles from Water Survey of Canada

# dictionary of basins
basins = OrderedDict() # maintain order
for name,basin in basins_info.iteritems():
  # add main basin
  basins[basin.name] = Basin(basin=basin, subbasin=None)
  if len(basin.subbasins) > 1 :
    # preserve grouping
    for subbasin in basin.subbasins[1:]: # skip first
      basins[subbasin] = Basin(basin=basin, subbasin=subbasin)
    

## Functions that handle access to ASCII files

def loadGageStation(basin=None, station=None, varlist=None, varatts=None, mode='climatology', 
                    filetype='monthly', folder=None, filename=None):
  ''' Function to load hydrograph climatologies for a given basin '''
  # resolve input
  if isinstance(basin,(basestring,BasinInfo)):
    if isinstance(basin,basestring):
      if basin in basins: basin = basins_info[basin]
      else: raise ValueError, 'Unknown basin: {}'.format(basin)
    folder = basin.folder
    if station is None: station = basin.maingage      
    elif not isinstance(station,basestring): raise TypeError
    if station in basin.stationfiles: filename = basin.stationfiles[station]
    else: raise ValueError, 'Unknown station: {}'.format(station)
    river = filename.split('_')[0].lower()
    atts = dict(basin=basin.name, river=river) # first component of file name       
  elif isinstance(folder,basestring) and isinstance(filename,basestring):
    atts = None; river = None
  else: raise TypeError, 'Specify either basin & station or folder & filename.'
  # variable attributes
  if varlist is None: varlist = variable_list
  elif not isinstance(varlist,(list,tuple)): raise TypeError  
  if varatts is None: varatts = deepcopy(variable_attributes.copy()) # because of nested dicts
  elif not isinstance(varatts,dict): raise TypeError
  # create dataset for station
  dataset = StationDataset(name=station, title=filename.split('.')[0], ID=None, varlist=[], atts=atts) 
  if mode == 'climatology': 
    # make common time axis for climatology
    te = 12 # length of time axis: 12 month
    climAxis = Axis(name='time', units='month', length=12, coord=np.arange(1,te+1,1)) # monthly climatology
  else: raise NotImplementedError, 'Currently only climatologies are supported.'
  dataset.addAxis(climAxis, copy=False)
  # a little helper function
  def makeVariable(varname, linesplit):  
    atts = varatts[varname] # these are more specific than below (mean/min/max)
    data = np.asarray(linesplit[1:te+1], dtype='float')
    if 'scalefactor' in atts: data = data * atts.pop('scalefactor')
    if 'fileunits' in atts: atts.pop('fileunits') 
    #print varname, data.shape, len(climAxis)
    return Variable(axes=[climAxis], data=data, **atts)      
  # open namelist file for reading   
  filehandle = fileinput.FileInput(['{}/{}'.format(folder,filename)], mode='r')  
  # parse file and load variables
  l = 0; filevar = None; lmean = False; lreadVar = False; offset = 0
  for line in filehandle:
    l += 1 # count lines...
    linesplit = line.split()
    # blank line
    if len(linesplit) == 0:
      if filevar is None: 
        if offset == 0: l -= 1 # empty header lines
        else: offset += 1 # empty lines after header
      else:
        if not lreadVar or lmean: offset = l # go to next record
        else: raise ParseError, 'Data not found at line {}.'.format(l)    
    # first line of file
    elif l == 1:
      if basin is not None: # check
        fileriver = linesplit[0].lower()
        if fileriver != river: raise ParseError, 'Inconsistent river names: {} != {}'.format(fileriver,river)
      tmp = linesplit[-1]
      if tmp[0] == '(' and tmp[-1] == ')': 
        ID = tmp[1:-1]; print('Station ID: {}'.format(ID))
      else: 
        ID = None; warn('No station ID available.')
      dataset.ID = ID # set station ID
      offset = 1
    # first line of record
    elif l == 1 + offset:
      if filetype == 'monthly':
        if not linesplit[0].lower() == 'monthly': raise ParseError, 'Unknown filetype; not monthly.'
      filevar = linesplit[2].lower() # third field       
      if filevar in varatts and filevar in varlist: 
        lreadVar = True # read this variable
        tmpatts = varatts[filevar]
        units = tmpatts.pop('fileunits',tmpatts['units'])        
        fileunits = linesplit[-1].lower()
        if units == fileunits[1:-1]: pass
        elif fileunits[0] == '(' and fileunits[-1] == ')' and units == fileunits[1:-1]: pass         
        else: raise ParseError,'No compatible units found; expected {}, found {}.'.format(units,fileunits)
      else:
        lreadVar = False # skip this variables
        if filevar in varatts: print('Skipping variable: {}.'.format(filevar))  
        else: print('Unknown variable: {}.'.format(filevar))
    # third line
    elif l == 2 + offset:      
      if filetype == 'monthly':
        if not ( linesplit[0].lower() == 'year' and len(linesplit) == 14 ): 
          raise ParseError, 'Unknown file format; expected yearly rows.'
    # skip the entire time-series section
    # extract variables (min/max/mean are separate variables)
    # load mean
    elif l > 2 + offset and linesplit[0].lower() == 'mean' and lreadVar:
      if filevar == 'discharge': varname = filevar
      dataset.addVariable(makeVariable(varname, linesplit), copy=False)
      lmean = True 
    # load maximum
    elif l > 2 + offset and linesplit[0].lower() == 'max' and lreadVar:
      if filevar == 'discharge': varname = 'discmax' # name is only temporary (see varatts)
      dataset.addVariable(makeVariable(varname, linesplit), copy=False) 
    # load minimum
    elif l > 2 + offset and linesplit[0].lower() == 'min' and lreadVar:
      if filevar == 'discharge': varname = 'discmin'
      dataset.addVariable(makeVariable(varname, linesplit), copy=False)
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
  
  basin_name = 'ARB'
    
  # verify basin info
  basin_info = basins_info[basin_name]
  print basin_info.long_name
  print basin_info.stationfiles
  
  # load basins
  basin = basins[basin_name]
  print basin.long_name
  print basin
  assert basin.info == basin_info
  assert basin.shapetype == 'BSN'
  
  # load station data
  station = basin.getMainGage()
  assert station.ID == loadGageStation(basin=basin_name).ID
  print
  print station
  print
  print station.discharge.getArray()
  
  # print basins
  print
  for bsn in basins.iterkeys():
    print bsn