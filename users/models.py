import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password, **extra_fields):
        email = self.normalize_email(email)
        return User.objects.create(
            email=email, password=make_password(password), **extra_fields
        )

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    name = models.CharField(
        verbose_name="이름",
        max_length=50,
    )
    email = models.EmailField(
        verbose_name="이메일",
        max_length=100,
        unique=True,
    )
    password = models.CharField(
        verbose_name="비밀 번호",
        max_length=255,
    )
    date_joined = models.DateTimeField(
        verbose_name="가입일",
        default=timezone.now,
    )
    uuid = models.UUIDField(
        verbose_name="유저 UUID",
        default=uuid.uuid4,
        editable=False,
    )
    is_active = models.BooleanField(
        verbose_name="계정 활성 여부",
        default=True,
    )
    is_staff = models.BooleanField(
        verbose_name="스태프 권한",
        default=False,
    )
    is_superuser = models.BooleanField(
        verbose_name="관리자 권한",
        default=False,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        db_table = "users"

    def __str__(self):
        return self.email
