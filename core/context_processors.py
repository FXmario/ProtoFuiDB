from Databases.models import Database


def databases_context(request):
    if request.user.is_authenticated:
        return {"databases": Database.objects.all()}
    return {"databases": Database.objects.none()}