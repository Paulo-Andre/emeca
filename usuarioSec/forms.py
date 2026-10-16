from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

User = get_user_model()


class AccountSignupForm(forms.ModelForm):
    password = forms.CharField(
        label="Senha",
        max_length=128,
        widget=forms.PasswordInput(),
        help_text="Use uma senha forte que atenda às regras de segurança do sistema.",
    )

    class Meta:
        model = User
        fields = ("username", "email", "password")

    def clean_password(self):
        password = self.cleaned_data["password"]
        user = self.instance
        user.username = self.cleaned_data.get("username", "")
        user.email = self.cleaned_data.get("email", "")
        validate_password(password, user=user)
        return password
