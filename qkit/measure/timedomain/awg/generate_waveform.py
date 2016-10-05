'''
generate_waveform.py
M. Jerger, S. Probst, A. Schneider (04/2015), J. Braumueller (04/2016)
'''

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

#import qt
import numpy as np
#import os.path
import time
import logging
import numpy
import sys
import scipy.special

# creates dummy objects to have everything well-defined.
#global sample
#sample = type('Sample', (object,),{  'exc_T' : 1e-6 , 'tpi' : 2e-9 , 'tpi2' : 1e-9, 'clock' : 1e9   })


def compensate(wfm, gamma, sample):
    '''
    Function that translates a given (analog) waveform wfm into a waveform wfc that needs to be programmed to the AWG
    to effectively obtain the waveform wfm after the bias T.
    This compensation is required due to the finite time constant of the bias Ts capacitor. The time constant in seconds 
    is passed to the function as gamma.
    Credits to A. Schneider
    
    Inputs:
        - wfm: original waveform to be compensated
        - gamma: bias T time constant in seconds
        - sample: sample object form which the function reads the AWG clock
    Outputs:
        - wfc: corrected waveform to be loaded to the AWG
    '''
    wfc = np.zeros_like(wfm)
    dif = np.diff(wfm)
    for i in range(1,len(wfm)):
        wfc[i]=wfc[i-1]+wfm[i-1]/(sample.clock*gamma)+dif[i-1]
    return wfc


def erf(pulse, attack, decay, sample, length=None, position = None, low=0, high=1, clock = None):
    '''
        create an erf-shaped envelope function
        erf(\pm 2) is almost 0/1, erf(\pm 1) is ~15/85%
        
        Input:
            tstart, tstop - erf(-2) times
            attack, decay - attack/decay times
    '''
    if(clock == None): clock = sample.clock
    if(length == None): length = sample.exc_T
    if position == None:
        position = length
        try: position -= sample.overlap
        except NameError: pass #if sample.overlap does not exist
    if(pulse>position):
        logging.error(__name__ + ' : pulse does not fit into waveform')
        
    sample_start = int(clock*(position-pulse))
    sample_end = int(clock*position)
    sample_length = int(np.round(length*clock))
    wfm = low * np.ones(sample_length)
    
    if attack != 0:
        if attack < 2./clock:
            logging.warning(__name__ + ' : attack too small compared to AWG sample frequency, setting to %.4g s'%(2./clock))
            attack = 2./clock
        nAttack = int(clock*attack)
        sAttack = 0.5*(1+scipy.special.erf(np.linspace(-2, 2, nAttack)))
        wfm[sample_start:sample_start+nAttack] += sAttack * (high-low)
    else:
        nAttack = 0
    if decay != 0:
        if decay < 2./clock:
            logging.warning(__name__ + ' : decay too small compared to AWG sample frequency, setting to %.4g s'%(2./clock))
            decay = 2./clock
        nDecay = int(clock*decay)
        sDecay = 0.5*(1+scipy.special.erf(np.linspace(2, -2, nDecay)))
        wfm[sample_end-nDecay:sample_end] += sDecay * (high-low)
    else:
        nDecay = 0
    wfm[sample_start+nAttack:sample_end-nDecay] = high
    return wfm
    
def exp(pulse, decay, sample, position = None, low=0, high=1, clock = None):
    '''
    create and exponential decaying waveform
    '''
    if(clock == None): clock = sample.clock
    if position == None:
        position = sample.exc_T
        try: position -= sample.overlap
        except NameError: pass #if sample.overlap does not exist
    sample_length = int(np.ceil(sample.exc_T*clock))
    wfm = low * np.ones(sample_length)
    sample_start = int(clock*(position-pulse))
    sample_end = int(clock*position)
    
    wfm[sample_start:sample_end] += np.exp(-np.arange(sample_end-sample_start)/(decay*clock)) * (high-low)
    return wfm
    
def triangle(attack, decay, sample, length = None, position = None, low=0, high=1, clock = None):
    '''
        create a pulse with triangular shape
        
        Input:
            attack, decay - attack and decay times in sec
            length - length of the comlete resulting waveform in sec
            position - position of the end of the pulse
    '''
    if(clock == None): clock = sample.clock
    if(length == None): length = sample.exc_T
    if position == None:
        position = length
        try: position -= sample.overlap
        except NameError: pass #if sample.overlap does not exist
    sample_start = int(clock*(position-attack-decay))
    sample_end = int(clock*position)
    sample_length = int(np.ceil(length*clock))
    sample_attack = int(np.ceil(attack*clock)) 
    sample_decay = int(np.ceil(decay*clock))
    wfm = low * np.ones(sample_length)
    wfm[sample_start:sample_start+sample_attack] = np.linspace(low, high, sample_attack)
    wfm[sample_start+sample_attack:sample_end-sample_decay] = high
    wfm[sample_end-sample_decay:sample_end] = np.linspace(high, low, sample_decay)
    return wfm

def square(pulse, sample, length = None,position = None, low = 0, high = 1, clock = None, adddelay=0.,freq=None):
    '''
        generate waveform corresponding to a dc pulse

        Input:
            pulse - pulse duration in seconds
            length - length of the generated waveform
            position - time instant of the end of the pulse
            low - pulse 'off' sample value
            high - pulse 'on' sample value
            clock - sample rate of the DAC
        Output:
            float array of samples
    '''
    if(clock == None): clock= sample.clock
    if(length == None): length= sample.exc_T
    if position == None:
        position = length
        try: position -= sample.overlap   #automatically correct overlap only when position argument not explicitly given
        except NameError: pass #if sample.overlap does not exist
    if(pulse>position): logging.error(__name__ + ' : pulse does not fit into waveform')
    sample_start = int(clock*(position-pulse-adddelay))
    sample_end = int(clock*(position-adddelay))
    sample_length = int(np.round(length*clock)/4)*4 #Ensures that the number of samples is divisible by 4 @andre20150615
    #sample_length = int(np.ceil(length*clock)) #old definition
    wfm = low*np.ones(sample_length)
    if(sample_start < sample_end): wfm[int(sample_start)] = high + (low-high)*(sample_start-int(sample_start))
    if freq==None: wfm[int(np.ceil(sample_start)):int(sample_end)] = high
    else:
        for i in range(int(sample_end)-int(np.ceil(sample_start))):
            wfm[i+int(np.ceil(sample_start))] = high*np.sin(2*np.pi*freq/clock*(i))
    if(np.ceil(sample_end) != np.floor(sample_end)): wfm[int(sample_end)] = low + (high-low)*(sample_end-int(sample_end))
    return wfm
    
    
def gauss(pulse, sample, length = None,position = None, low = 0, high = 1, clock = None):
    '''
        generate waveform corresponding to a dc gauss pulse

        Input:
            pulse - pulse duration in seconds
            length - length of the generated waveform
            position - time instant of the end of the pulse
            low - pulse 'off' sample value
            high - pulse 'on' sample value
            clock - sample rate of the DAC
        Output:
            float array of samples
    '''
    if(clock == None): clock= sample.clock
    if(length == None): 
        length= sample.exc_T
        sample_length = int(np.round(length*clock)/4)*4
    else:
        sample_length = int(length*clock)
    if position == None:
        position = length
        try: position -= sample.overlap
        except NameError: pass #if sample.overlap does not exist
    if(pulse>position): logging.error(__name__ + ' : pulse does not fit into waveform')
    sample_start = int(clock*(position-pulse))
    sample_end = int(clock*position)
    
    wfm = low*np.ones(sample_length)
    if(sample_start < sample_end): wfm[int(sample_start)] = 0.#high + (low-high)*(sample_start-int(sample_start))
    #wfm[int(np.ceil(sample_start)):int(sample_end)] = high
    pulsesamples = int(int(sample_end)-int(sample_start))
    for i in range(pulsesamples):
        wfm[np.ceil(sample_start)+i] = high*np.exp(-(i-pulsesamples/2.)**2/(2.*(pulsesamples/5.)**2))
    if(np.ceil(sample_end) != np.floor(sample_end)): wfm[int(sample_end)] = low + (high-low)*(sample_end-int(sample_end))
    return wfm

def arb_function(function, pulse, length = None,position = None, clock = None):
    '''
        generate arbitrary waveform pulse

        Input:
            function - function called
            pulse - duration of the signal
            position - time instant of the end of the signal
            length - duration of the waveform
            clock - sample rate of the DAC
        Output:
            float array of samples
    '''
    if(clock == None): clock= sample.clock
    if(length == None): length= sample.exc_T
    if position == None:
        position = length
        try: position -= sample.overlap
        except NameError: pass #if sample.overlap does not exist
    if(pulse>position): logging.error(__name__ + ' : pulse does not fit into waveform')
    sample_start = clock*(position-pulse)
    sample_end = clock*position
    sample_length = int(np.ceil(length*clock))

    wfm = np.zeros(sample_length)
    times = 1./clock*np.arange(0, sample_end-sample_start+1)
    wfm[sample_start:sample_end] = function(times)
    return wfm

    
def t1(delay, sample, length = None, low = 0, high = 1, clock = None):
    '''
        generate waveform with one pi pulse and delay after

        Input:
            delay - time delay after pi pulse
            sample object

        Output:
            float array of samples
    '''
    if(clock == None): clock = sample.clock
    if(length == None): length = sample.exc_T
    try: delay += sample.overlap
    except NameError: pass #if sample.overlap does not exist
    if(delay+sample.tpi > length): logging.error(__name__ + ' : pulse does not fit into waveform')
    
    wfm = square(sample.tpi, sample, length, length-delay, clock = clock)
    wfm = wfm * (high-low) + low
    return wfm
    
    
def ramsey(delay, sample, pi2_pulse = None, length = None,position = None, low = 0, high = 1, clock = None):
    '''
        generate waveform with two pi/2 pulses and delay in-between

        Input:
            delay - time delay between the pi/2 pulses
            pi2_pulse - length of a pi/2 pulse
            (see awg_pulse for rest)
        Output:
            float array of samples
    '''
    if(clock == None): clock = sample.clock
    if(length == None): length = sample.exc_T
    if(position == None): position = length
    try: position -= sample.overlap
    except NameError: pass #if sample.overlap does not exist
    if(pi2_pulse == None): pi2_pulse = sample.tpi2
    if(delay+2*pi2_pulse>position): logging.error(__name__ + ' : ramsey pulses do not fit into waveform')
    wfm = square(pi2_pulse, sample, length, position, clock = clock)
    wfm += square(pi2_pulse, sample,  length, position-delay-pi2_pulse, clock = clock)
    wfm = wfm * (high-low) + low
    return wfm


def spinecho(delay, sample, pi2_pulse = None, pi_pulse = None, length = None,position = None, low = 0, high = 1, clock = None, readoutpulse=True,adddelay=0., freq=None, n = 1):
    '''
        generate waveform with two pi/2 pulses at the ends and a number n of echo (pi) pilses in between
        pi2 - delay/n - pi - delay/n - pi - ... - pp - delay/n - [pi2, if readoutpulse]
        
        pulse - pulse duration in seconds
        length - length of the generated waveform
        position - time instant of the end of the pulse
        low - pulse 'off' sample value
        high - pulse 'on' sample value
        clock - sample rate of the DAC
        
        waveforms are contructed from right to left
    '''
    
    if(clock == None): clock= sample.clock
    if(length == None): length= sample.exc_T
    if(position == None): position = length
    try: position -= sample.overlap
    except NameError: pass #if sample.overlap does not exist
    if(pi2_pulse == None): pi2_pulse = sample.tpi2
    if(pi_pulse == None): pi_pulse = sample.tpi
    
    if adddelay+delay+2*pi2_pulse+n*pi_pulse > position:
        logging.error(__name__ + ' : sequence does not fit into waveform. delay is the sum of the waiting times in between the pi pulses')
    if readoutpulse:   #last pi/2 pulse
        wfm = square(pi2_pulse, sample, length, position, clock = clock,freq=freq)   #add pi/2 pulse
    else:
        wfm = square(pi2_pulse, sample, length, position, low, low, clock,freq=freq)   #create space (low) of the length of a pi/2 pulse
    for ni in range(n):   #add pi pulses
        wfm += square(pi_pulse, sample, length, position - pi2_pulse - ni*pi_pulse - float(delay)/(n+1)*(ni+1) - adddelay, clock = clock, freq=freq)
    wfm += square(pi2_pulse, sample, length, position - pi2_pulse - n*pi_pulse - delay - adddelay, clock = clock, freq=freq)   #pi/2 pulse
    wfm = wfm * (high-low) + low   #adjust offset
    return wfm