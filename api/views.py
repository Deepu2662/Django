from api.models import Uploads

from django.shortcuts import render
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status

import subprocess
import numpy

from rest_framework import parsers, renderers
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth.signals import user_logged_in
from rest_framework.authtoken.serializers import AuthTokenSerializer
from django.db import transaction
from django.contrib.auth.models import User
from datetime import datetime

import base64
from io import BytesIO
from pydub import AudioSegment
from os.path import basename
from django.core.files import File

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

@api_view(['POST','GET'])
def upload_audio(request):
    try:
        print(request.user)
        file=request.FILES.get('audio')
        print(request.POST)
        print(request.FILES)
        if(request.POST.get('audio')):
            base64_to_audio(request.POST.get('audio'), "temp/output_audio.wav")
        up=Uploads()
        up.type=request.POST.get('type')
        up.aid=request.POST.get('aid')
        up.user=request.user
        if(request.POST.get('type')=="mob"):
            up.audio=file
        else:
            floc='temp/output_audio.wav'
            # with open(floc, 'rb') as file:
            #     audio_content = file.read()
            # audio_base64 = base64.b64encode(audio_content).decode('utf-8')
            up.audio.save(basename(floc), content=File(open(floc, 'rb')))
        
        up.save()
        return Response(data={"msg":"ok"},status=status.HTTP_200_OK)
    except Exception as e:
        print(e)
        data={}
        data['error']=str(e)
        return Response(data=data,status=status.HTTP_403_FORBIDDEN)
    


sample_time = 500# number of points to scan cross correlation over
span = 150# step size (in points) of cross correlation
step = 1# minimum number of points that must overlap in cross correlation
# exception is raised if this cannot be met
min_overlap = 20# report match when cross correlation has a peak exceeding threshold
threshold = 0.5
# calculate fingerprint
def calculate_fingerprints(filename):
    fpcalc_out = subprocess.getoutput('fpcalc -raw -length %i %s' % (sample_time, filename))
    print(fpcalc_out)
    fingerprint_index = fpcalc_out.find('FINGERPRINT=') + 12
    # convert fingerprint to list of integers
    fingerprints = list(map(int, fpcalc_out[fingerprint_index:].split(',')))      
    return fingerprints  
    # returns correlation between lists
def correlation(listx, listy):
    if len(listx) == 0 or len(listy) == 0:
        # Error checking in main program should prevent us from ever being
        # able to get here.     
        raise Exception('Empty lists cannot be correlated.')    
    if len(listx) > len(listy):     
        listx = listx[:len(listy)]  
    elif len(listx) < len(listy):       
        listy = listy[:len(listx)]      

    covariance = 0  
    for i in range(len(listx)):     
        covariance += 32 - bin(listx[i] ^ listy[i]).count("1")  
    covariance = covariance / float(len(listx))     
    return covariance/32  
    # return cross correlation, with listy offset from listx
def cross_correlation(listx, listy, offset):    
    if offset > 0:      
        listx = listx[offset:]      
        listy = listy[:len(listx)]  
    elif offset < 0:        
        offset = -offset        
        listy = listy[offset:]      
        listx = listx[:len(listy)]  
    if min(len(listx), len(listy)) < min_overlap:
        return   
    return correlation(listx, listy)  
    # cross correlate listx and listy with offsets from -span to span
def compare(listx, listy, span, step):  
    if span > min(len(listx), len(listy)):
        raise Exception('span >= sample size: %i >= %i\n' % (span, min(len(listx), len(listy))) + 'Reduce span, reduce crop or increase sample_time.')

    corr_xy = []    
    for offset in numpy.arange(-span, span + 1, step):      
        corr_xy.append(cross_correlation(listx, listy, offset)) 
    return corr_xy  
    # return index of maximum value in list
def max_index(listx):   
    max_index = 0   
    max_value = listx[0]    
    for i, value in enumerate(listx):       
        if value > max_value:           
            max_value = value           
            max_index = i   
    return max_index  

def get_max_corr(corr, source, target): 
    max_corr_index = max_index(corr)    
    max_corr_offset = -span + max_corr_index * step 
    print("max_corr_index = ", max_corr_index, "max_corr_offset = ", max_corr_offset)
    # report matches    
    if corr[max_corr_index] > threshold:        
        print(('%s and %s match with correlation of %.4f at offset %i' % (source, target, corr[max_corr_index], max_corr_offset))) 
    return corr[max_corr_index]

def correlate(source, target):  
    fingerprint_source = calculate_fingerprints(source) 
    print("a1",fingerprint_source)
    fingerprint_target = calculate_fingerprints(target)     
    print("a2",fingerprint_target)
    corr = compare(fingerprint_source, fingerprint_target, span, step)  
    max_corr_offset = get_max_corr(corr, source, target) 
    print(max_corr_offset) 
    return max_corr_offset



class ObtainAuthTokenNew(APIView):
    throttle_classes = ()
    permission_classes = ()
    parser_classes = (parsers.FormParser,
                      parsers.MultiPartParser, parsers.JSONParser,)
    renderer_classes = (renderers.JSONRenderer,)
    serializer_class = AuthTokenSerializer

    def post(self, request, *args, **kwargs):
        try:
            serializer = self.serializer_class(data=request.data)
            serializer.is_valid(raise_exception=True)
            user = serializer.validated_data['user']
            print(user)
            if(not user.is_superuser):
                raise Exception("Invalid Admin Credentials")
            token, created = Token.objects.get_or_create(user=user)
            user_logged_in.send(sender=user.__class__, request=request, user=user)
            data = {}
            data['email'] = user.email
            data['token'] = token.key
            return Response(data=data,status=status.HTTP_200_OK)
        except Exception as e:
            data = {}
            data['error'] = True
            data['message'] = str(e)
            return Response(data=data,status=status.HTTP_401_UNAUTHORIZED)

obtain_auth_token_new = ObtainAuthTokenNew.as_view()

@api_view(['POST','GET'])
def check_audio(request):
    try:
        aid=request.POST.get("aid")
        audios=Uploads.objects.filter(aid=aid)
        data={}

        if(len(audios)==2):
            a1=str(audios[0].audio)
            a2=str(audios[1].audio)
            val=correlate(a1, a2)
            print(a1)
            print(a2)
            data['error']=False
            data['corr']=val
            data['match']=val>0.8
            return Response(data=data,status=status.HTTP_200_OK)
        else:
            data['error']=True
            data['message']="Invalid data"
            return Response(data=data,status=status.HTTP_412_PRECONDITION_FAILED)

    except Exception as e:
        data = {}
        data['error'] = True
        data['message'] = str(e)
        return Response(data=data,status=status.HTTP_401_UNAUTHORIZED)

def base64_to_audio(base64_string, output_file=None):
    # Decode the base64 string to binary data
    audio_data = base64.b64decode(base64_string)
    
    # Convert binary data to BytesIO object
    # audio_stream = BytesIO(audio_data)
    
    # Load audio data from BytesIO object
    # audio_segment = AudioSegment.from_file(audio_stream)
    
    # Play the audio
    # audio_segment.export("output_audio.wav", format="wav").play()
    
    # Save the audio to a file if specified
    if output_file:
        with open(output_file, "wb") as f:
            f.write(audio_data)

def receive_fcm_token(request):
    if request.method == 'POST':
        fcm_token = request.POST.get('fcm_token')
        
        # Do something with the FCM token, such as storing it in the database
        # You can associate the FCM token with a user or device as needed

        return JsonResponse({'message': 'FCM token received successfully'})
    else:
        return JsonResponse({'error': 'Invalid request method'})
    
def send_fcm_notification(self, user):
        try:
            # Replace 'your_server_key' with your Firebase Cloud Messaging server key
            server_key = 'your_server_key'

            # Get the user's FCM devices
            devices = FCMDevice.objects.filter(user=user)

            # Send a notification to each device
            for device in devices:
                device.send_message(title='Login Alert', body='Someone is trying to log in to your account.')

        except Exception as e:
            print("Error sending FCM notification:", e)