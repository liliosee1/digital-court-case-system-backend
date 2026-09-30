from django.db.models import Q
from django.utils import timezone
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import Case, CaseHistory, CaseParty, Courtroom, Hearing, Party, Role, User


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = "__all__"


class UserSerializer(serializers.ModelSerializer):
    # Only basic, non-secret fields are available for API responses.
    role = serializers.CharField(source="role.name", read_only=True)

    class Meta:
        model = User
        fields = ("id", "full_name", "email", "phone", "role")


class UserManagementSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, max_length=128)
    role = serializers.PrimaryKeyRelatedField(queryset=Role.objects.all())

    class Meta:
        model = User
        fields = (
            "id", "full_name", "email", "password", "phone", "role",
            "created_at", "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate(self, attrs):
        if self.instance is None and not attrs.get("password"):
            raise serializers.ValidationError({"password": "This field is required."})
        return attrs

    def validate_password(self, value):
        user = self.instance
        if user is None:
            user = User(
                full_name=self.initial_data.get("full_name", ""),
                email=self.initial_data.get("email", ""),
            )
        try:
            validate_password(value, user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value

    def validate_role(self, role):
        request = self.context.get("request")
        role_is_admin = role.name.casefold() == "administrator"
        if (
            self.instance is not None
            and request is not None
            and self.instance.pk == request.user.pk
            and not role_is_admin
        ):
            raise serializers.ValidationError(
                "You cannot remove the Administrator role from your own account."
            )
        if (
            self.instance is not None
            and self.instance.role.name.casefold() == "administrator"
            and not role_is_admin
            and User.objects.filter(role__name__iexact="Administrator").count() <= 1
        ):
            raise serializers.ValidationError(
                "The last Administrator account must remain an Administrator."
            )
        return role

    def create(self, validated_data):
        password = validated_data.pop("password")
        now = timezone.now()
        user = User(
            **validated_data,
            password_hash=make_password(password),
            created_at=now,
            updated_at=now,
        )
        user.save(force_insert=True)
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        update_fields = list(validated_data)
        if password:
            instance.password_hash = make_password(password)
            update_fields.append("password_hash")
        if update_fields:
            instance.updated_at = timezone.now()
            update_fields.append("updated_at")
            instance.save(update_fields=update_fields)
        return instance


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(
        write_only=True, trim_whitespace=False, max_length=128
    )


class CaseSerializer(serializers.ModelSerializer):
    assigned_judge = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.select_related("role").all(),
        allow_null=True,
        required=False,
    )
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    assigned_judge_name = serializers.CharField(
        source="assigned_judge.full_name", read_only=True, allow_null=True
    )
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True)

    class Meta:
        model = Case
        fields = (
            "id",
            "case_number",
            "case_type",
            "title",
            "description",
            "filing_date",
            "status",
            "assigned_judge",
            "assigned_judge_name",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_by", "created_at", "updated_at")

    def validate_assigned_judge(self, judge):
        if judge is not None and judge.role.name.casefold() != "judge":
            raise serializers.ValidationError("The assigned user must have the Judge role.")
        return judge


class PartySerializer(serializers.ModelSerializer):
    class Meta:
        model = Party
        fields = ("id", "full_name", "party_type", "phone", "email", "address", "created_at")
        read_only_fields = ("id", "created_at")


class CasePartySerializer(serializers.ModelSerializer):
    case_number = serializers.CharField(source="case.case_number", read_only=True)
    party_name = serializers.CharField(source="party.full_name", read_only=True)

    class Meta:
        model = CaseParty
        fields = ("id", "case", "case_number", "party", "party_name")
        read_only_fields = ("id",)


class CourtroomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Courtroom
        fields = ("id", "name", "location", "capacity", "status")
        read_only_fields = fields


class HearingSerializer(serializers.ModelSerializer):
    case = serializers.PrimaryKeyRelatedField(
        queryset=Case.objects.select_related("assigned_judge")
    )
    judge = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role__name__iexact="Judge")
    )
    case_number = serializers.CharField(source="case.case_number", read_only=True)
    case_title = serializers.CharField(source="case.title", read_only=True)
    judge_name = serializers.CharField(source="judge.full_name", read_only=True)
    courtroom_name = serializers.CharField(source="courtroom.name", read_only=True)
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Hearing
        fields = (
            "id", "case", "case_number", "case_title", "judge", "judge_name",
            "courtroom", "courtroom_name", "hearing_date", "hearing_time",
            "status", "notes", "created_by", "created_at", "updated_at",
        )
        read_only_fields = ("id", "created_by", "created_at", "updated_at")

    def validate_status(self, value):
        allowed_statuses = {"scheduled", "completed", "cancelled", "adjourned"}
        if value.casefold() not in allowed_statuses:
            raise serializers.ValidationError(
                "Choose Scheduled, Completed, Cancelled, or Adjourned."
            )
        return value

    def validate(self, attrs):
        instance = self.instance
        case = attrs.get("case", getattr(instance, "case", None))
        judge = attrs.get("judge", getattr(instance, "judge", None))
        room = attrs.get("courtroom", getattr(instance, "courtroom", None))
        hearing_date = attrs.get("hearing_date", getattr(instance, "hearing_date", None))
        hearing_time = attrs.get("hearing_time", getattr(instance, "hearing_time", None))
        status = attrs.get("status", getattr(instance, "status", "Scheduled"))

        if case and case.assigned_judge_id and case.assigned_judge_id != judge.pk:
            raise serializers.ValidationError({
                "judge": "The hearing judge must match the judge assigned to this case."
            })

        if room and room.status.casefold() != "available":
            raise serializers.ValidationError({
                "courtroom": "This courtroom is not available for scheduling."
            })

        # Lock the judge and room while checking and saving the schedule. This
        # prevents two concurrent requests from booking the same resource.
        request = self.context.get("request")
        if request is not None and request.method in ("POST", "PUT", "PATCH"):
            if judge:
                User.objects.select_for_update().filter(pk=judge.pk).exists()
            if room:
                Courtroom.objects.select_for_update().filter(pk=room.pk).exists()

        schedule_fields = ("hearing_date", "hearing_time", "judge", "courtroom")
        schedule_changed = instance is None or any(
            field in attrs and attrs[field] != getattr(instance, field)
            for field in schedule_fields
        )
        if instance is not None and status.casefold() == "scheduled":
            previous_status = instance.status.casefold()
            if previous_status in {"cancelled", "completed"}:
                schedule_changed = True
        if (
            status.casefold() == "scheduled"
            and hearing_date
            and hearing_date < timezone.localdate()
        ):
            raise serializers.ValidationError({
                "hearing_date": "A new scheduled hearing must be today or in the future."
            })

        if schedule_changed and hearing_date and hearing_time and judge and room:
            conflicts = Hearing.objects.filter(
                hearing_date=hearing_date,
                hearing_time=hearing_time,
            ).exclude(status__iexact="Cancelled").exclude(status__iexact="Completed")
            if instance is not None:
                conflicts = conflicts.exclude(pk=instance.pk)
            conflicts = conflicts.filter(
                Q(courtroom_id=room.pk) | Q(judge_id=judge.pk)
            )
            if conflicts.exists():
                raise serializers.ValidationError({
                    "hearing_time": "The judge or courtroom already has a hearing at this time."
                })

        return attrs


class CaseHistorySerializer(serializers.ModelSerializer):
    case_number = serializers.CharField(source="case.case_number", read_only=True)
    user_name = serializers.CharField(source="user.full_name", read_only=True)

    class Meta:
        model = CaseHistory
        fields = ("id", "case", "case_number", "user", "user_name", "action", "description", "created_at")
        read_only_fields = fields
