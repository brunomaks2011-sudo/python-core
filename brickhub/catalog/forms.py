from django import forms

from .models import Review


class ReviewForm(forms.ModelForm):
    rating = forms.TypedChoiceField(label="Оцінка", coerce=int, choices=[(i, str(i)) for i in range(5, 0, -1)],
                                    widget=forms.RadioSelect)

    class Meta:
        model = Review
        fields = ["rating", "title", "text"]
        widgets = {
            "title": forms.TextInput(attrs={"maxlength": 120, "placeholder": "Коротко про головне"}),
            "text": forms.Textarea(attrs={"rows": 4, "maxlength": 3000,
                                          "placeholder": "Що сподобалось, що ні, кому радите"}),
        }
