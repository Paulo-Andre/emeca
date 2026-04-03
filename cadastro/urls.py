
from django.urls import path 
from . import views

urlpatterns = [
    path('matricula/',views.cadastrar, name="matricula"),
    
    
    
   
]
