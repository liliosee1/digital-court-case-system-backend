from django.db import models


class Role(models.Model):
    name = models.CharField(max_length=50, unique=True)

    class Meta:
        managed = False
        db_table = 'roles'

    def __str__(self):
        return self.name


class User(models.Model):
    full_name = models.CharField(max_length=100)
    email = models.CharField(max_length=100, unique=True)
    password_hash = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, blank=True, null=True)
    role = models.ForeignKey(
        Role,
        on_delete=models.DO_NOTHING
    )
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'users'

    def __str__(self):
        return self.full_name


class Case(models.Model):
    case_number = models.CharField(max_length=50, unique=True)
    case_type = models.CharField(max_length=50)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    filing_date = models.DateField()
    status = models.CharField(max_length=50)
    assigned_judge = models.ForeignKey(
        User,
        on_delete=models.DO_NOTHING,
        blank=True,
        null=True,
        related_name='assigned_cases'
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.DO_NOTHING,
        db_column='created_by',
        related_name='created_cases'
    )
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'cases'

    def __str__(self):
        return self.case_number


class Party(models.Model):
    full_name = models.CharField(max_length=150)
    party_type = models.CharField(max_length=50)
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.CharField(max_length=100, blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'parties'

    def __str__(self):
        return self.full_name


class CaseParty(models.Model):
    case = models.ForeignKey(
        Case,
        on_delete=models.DO_NOTHING
    )
    party = models.ForeignKey(
        Party,
        on_delete=models.DO_NOTHING
    )

    class Meta:
        managed = False
        db_table = 'case_parties'
        unique_together = ('case', 'party')


class Courtroom(models.Model):
    name = models.CharField(max_length=100, unique=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    capacity = models.IntegerField(blank=True, null=True)
    status = models.CharField(max_length=30)

    class Meta:
        managed = False
        db_table = 'courtrooms'

    def __str__(self):
        return self.name


class Hearing(models.Model):
    case = models.ForeignKey(
        Case,
        on_delete=models.DO_NOTHING
    )
    judge = models.ForeignKey(
        User,
        on_delete=models.DO_NOTHING,
        related_name='hearings_as_judge'
    )
    courtroom = models.ForeignKey(
        Courtroom,
        on_delete=models.DO_NOTHING
    )
    hearing_date = models.DateField()
    hearing_time = models.TimeField()
    status = models.CharField(max_length=50)
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.DO_NOTHING,
        db_column='created_by',
        related_name='created_hearings'
    )
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'hearings'


class CaseHistory(models.Model):
    case = models.ForeignKey(
        Case,
        on_delete=models.DO_NOTHING
    )
    user = models.ForeignKey(
        User,
        on_delete=models.DO_NOTHING
    )
    action = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'case_history'
