from django.db import models


class Service(models.Model):
    nom = models.CharField(max_length=150)
    code = models.CharField(max_length=10, unique=True)
    description = models.TextField(blank=True)
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ["nom"]

    def __str__(self):
        return f"{self.code} - {self.nom}"