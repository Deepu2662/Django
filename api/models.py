from django.db import models
from django.contrib.auth.models import User

# Create your models here.
class Uploads(models.Model):
    user=models.ForeignKey(to=User,on_delete=models.DO_NOTHING)
    audio=models.FileField(upload_to='audio')
    type=models.CharField(max_length=10)
    aid=models.CharField(max_length=10)
    