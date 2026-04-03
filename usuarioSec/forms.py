from django import forms
from django.contrib.auth import get_user_model
User = get_user_model()

class AccountSignupForm(forms.ModelForm):
    password =forms.CharField(
        label="Senha",
        max_length=20,
        widget=forms.PasswordInput()
    )
    class Meta:
        model=User
        fields = ('username','email','password',)