from django.conf import settings
from django.db import models
from django.utils import timezone


class Child(models.Model):
    parent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="children")
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    age_months = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Возраст (в месяцах)")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        full = f"{self.first_name} {self.last_name}".strip()
        return full or f"Child #{self.pk}"


class ChildProfile(models.Model):
    """Анкета ребёнка — заполняется один раз, используется для всех опросов."""

    parent = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="child_profiles"
    )
    child_name = models.CharField(max_length=120, verbose_name="Имя ребёнка")
    birth_date = models.DateField(verbose_name="Дата рождения")
    gender = models.CharField(max_length=20, blank=True, verbose_name="Пол")

    address = models.CharField(max_length=300, blank=True, verbose_name="Адрес")
    phone = models.CharField(max_length=30, blank=True, verbose_name="Телефон")

    FILLED_BY_CHOICES = [
        ("mother", "мать"),
        ("father", "отец"),
        ("grandmother", "бабушка"),
        ("other_family", "другой член семьи"),
        ("nanny", "няня / воспитатель"),
    ]
    filled_by = models.CharField(
        max_length=20, choices=FILLED_BY_CHOICES, blank=True, verbose_name="Кто заполняет"
    )

    birth_week = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Неделя рождения")

    BIRTH_CONDITIONS_CHOICES = [
        ("normal", "нормальные"),
        ("child_complications", "осложнения для ребенка"),
        ("mother_complications", "осложнения для матери"),
        ("both_complications", "осложнения для обоих"),
    ]
    birth_conditions = models.CharField(
        max_length=30, choices=BIRTH_CONDITIONS_CHOICES, blank=True, verbose_name="Условия рождения"
    )

    CHILD_HEALTH_CHOICES = [
        ("healthy", "здоров"),
        ("recovered", "полностью выздоровел после тяжелой болезни"),
        ("weakened", "ослаблен после тяжелой болезни"),
        ("ill", "физически болен"),
    ]
    child_health = models.CharField(
        max_length=20, choices=CHILD_HEALTH_CHOICES, blank=True, verbose_name="Состояние здоровья"
    )
    seizures = models.BooleanField(default=False, verbose_name="Судороги")

    WHERE_GROWS_CHOICES = [
        ("family", "в семье"),
        ("family_nursery", "в семье и яслях/садике"),
        ("nursery_24", "в круглосуточных яслях"),
        ("orphanage", "в детском доме"),
    ]
    where_child_grows = models.CharField(
        max_length=20, choices=WHERE_GROWS_CHOICES, blank=True, verbose_name="Где растёт ребёнок"
    )

    FAMILY_LANGUAGE_CHOICES = [
        ("russian_only", "только русский"),
        ("russian_other", "русский и другой"),
    ]
    family_language = models.CharField(
        max_length=20, choices=FAMILY_LANGUAGE_CHOICES, blank=True, verbose_name="Язык в семье"
    )
    children_count = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Количество детей в семье")

    CAREGIVER_CHOICES = [
        ("mother", "мать"),
        ("father", "отец"),
        ("grandmother", "бабушка"),
        ("other_family", "другой член семьи"),
        ("nanny", "няня / воспитатель"),
    ]
    main_caregiver = models.CharField(
        max_length=20, choices=CAREGIVER_CHOICES, blank=True, verbose_name="Основной уход"
    )

    CAREGIVER_MOOD_CHOICES = [
        ("cheerful", "бодрое"),
        ("calm", "спокойное"),
        ("irritated", "раздраженное"),
        ("depressed", "подавленное"),
    ]
    caregiver_mood = models.CharField(
        max_length=20, choices=CAREGIVER_MOOD_CHOICES, blank=True, verbose_name="Настроение ухаживающего"
    )

    CAREGIVER_VALUES_CHOICES = [
        ("obedience", "послушание"),
        ("sociability", "общительность"),
        ("curiosity", "любопытство"),
    ]
    caregiver_values = models.CharField(
        max_length=20, choices=CAREGIVER_VALUES_CHOICES, blank=True, verbose_name="Ценности ухаживающего"
    )

    ECONOMIC_STATUS_CHOICES = [
        ("good", "хорошее"),
        ("average", "среднее"),
        ("poor", "плохое"),
        ("very_poor", "очень плохое"),
    ]
    economic_status = models.CharField(
        max_length=20, choices=ECONOMIC_STATUS_CHOICES, blank=True, verbose_name="Материальное положение"
    )

    mother_age = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Возраст матери")
    father_age = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Возраст отца")
    caregiver_age = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="Возраст ухаживающего")

    EDUCATION_CHOICES = [
        (1, "неполное среднее"),
        (2, "среднее"),
        (3, "среднее специальное"),
        (4, "неполное высшее"),
        (5, "высшее"),
    ]
    mother_education = models.PositiveSmallIntegerField(
        null=True, blank=True, choices=EDUCATION_CHOICES, verbose_name="Образование матери"
    )
    father_education = models.PositiveSmallIntegerField(
        null=True, blank=True, choices=EDUCATION_CHOICES, verbose_name="Образование отца"
    )
    caregiver_education = models.PositiveSmallIntegerField(
        null=True, blank=True, choices=EDUCATION_CHOICES, verbose_name="Образование ухаживающего"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Анкета ребёнка"
        verbose_name_plural = "Анкеты детей"

    def __str__(self) -> str:
        return self.child_name

    def age_months(self) -> int | None:
        if not self.birth_date:
            return None
        today = timezone.now().date()
        return max(0, (today.year - self.birth_date.year) * 12 + (today.month - self.birth_date.month))

    def age_months_float(self) -> float | None:
        """Дробный возраст в месяцах (для сопоставления с нормами)."""
        if not self.birth_date:
            return None
        today = timezone.now().date()
        days = (today - self.birth_date).days
        if days < 0:
            return 0.0
        return round(days / (365.25 / 12), 2)
