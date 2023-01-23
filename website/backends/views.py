import calendar
import datetime

import pandas as pd
import requests
from dateutil import parser
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.core.exceptions import ObjectDoesNotExist
from django.core.mail import send_mail, BadHeaderError
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import render, redirect

from .forms import CustomerForm, UserForm, LoginUserForm, ServiceForm, CreateDay
from .models import Date, Time, DayOfWeek, Service, RecordingTime


def home(request):
    return render(request, 'home.html', locals())


def news(request, temp_img=None):
    url = 'https://newsapi.org/v2/everything'
    headers = {
        'X-Api-Key': settings.APIKEY_NEWSAPI
    }

    params = {
        'q': 'car',
        'from': datetime.date.today(),
        'pageSize': 20
    }

    r = requests.get(url=url, params=params, headers=headers)

    data = r.json()
    if data["status"] != "ok":
        return HttpResponse("<h1>Request Failed</h1>")
    data = data["articles"]

    context = {
        "success": True,
        "data": [],
    }

    for i in data:
        time_str = parser.isoparse(i["publishedAt"])
        i["publishedAt"] = time_str.strftime('%A, %d %B %H:%M:%S')

        context["data"].append({
            "title": i["title"],
            "description": "" if i["description"] is None else i["description"],
            "url": i["url"],
            "image": temp_img if i["urlToImage"] is None else i["urlToImage"],
            "publishedat": i["publishedAt"]
        })

    return render(request, 'news.html', context=context)


def user_signup(request):
    error = ''
    if request.method == 'POST':
        user_form = UserForm(request.POST)

        if user_form.is_valid():
            user = user_form.save(commit=False)
            user_form.save()
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(request, "Вы успешно зарегестрировались")
            return redirect('/')
        else:
            messages.error(request, "Ошибка регистрации")
        context = {
            'user_form': user_form,
            'error': error
        }
    else:
        context = {
            'user_form': UserForm(),
            'error': error
        }
    return render(request, 'signup.html', context)


def user_login(request):
    if request.method == 'POST':
        form = LoginUserForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
        else:
            messages.error(request, "Неправильное имя пользователя/пароль!")
        return redirect('/')
    else:
        form = LoginUserForm()

    context = {
        'form': form
    }
    return render(request, 'login.html', context=context)


def user_logout(request):
    logout(request)
    return redirect('/')


def add_service(request, self=None):
    recording_time = RecordingTime.objects.all()

    if not request.user.is_authenticated:
        messages.error(request, "To connect the service you must be authorized!")
        return redirect('/accounts/login/')

    days = DayOfWeek.objects.all()

    if request.method == 'POST':
        form = ServiceForm(data=request.POST)
        if form.is_valid():
            data = form.save(commit=False)
            data.owner = request.user
            data.save()

            data.recording_time.add(request.POST['recording_time'])
            data.save()

            service = data.id
            list_of_days = request.POST.getlist('working_days')
            create_working_days(request, service, list_of_days)

            with transaction.atomic():
                for day in list_of_days:
                    days = DayOfWeek.objects.get(pk=day)
                    data.working_days.add(days)
                data.save()
        else:
            messages.error(request, "Вы указали неверные данные!")
        return redirect('/')
    else:
        form = ServiceForm()

    context = {
        'form': form,
        'days': days,
        'recording_times': recording_time,
    }
    return render(request, 'add_service.html', context=context)


def create_working_days(request, service_id, list_of_days):
    # индексы рабочих дней
    service_work_days = []
    for i in list_of_days:
        service_work_days.append(int(i))

    # все дни месяца
    total_list = []
    c = calendar.TextCalendar(calendar.MONDAY)
    for i in c.itermonthdays(datetime.datetime.today().year, datetime.datetime.today().month):
        total_list.append(i)
    total_list = list(filter(lambda num: num != 0, total_list))

    # рабочие дни сервиса
    total_work_days = []
    for i in total_list:
        obj = datetime.datetime(datetime.datetime.today().year, datetime.datetime.today().month, i).isoweekday()
        if obj not in service_work_days:
            continue
        else:
            total_work_days.append(i)

    with transaction.atomic():
        for i in total_work_days:
            Date.objects.create(day=i, service_id=service_id)

    return messages.success(request, "Сalendar with custom for your service successfully created")


def service_selection(request):
    services = Service.objects.all()

    context = {
        'services': services,

    }

    return render(request, 'list_of_services.html', context=context)


def day_selection(request, service_id):
    service = Service.objects.get(pk=service_id)
    day = Date.objects.filter(service_id=service_id).order_by('day')

    # HTML calendar
    list1 = []
    text_calendar = []
    c = calendar.TextCalendar(calendar.MONDAY)
    for i in c.itermonthdays(datetime.datetime.today().year, datetime.datetime.today().month):
        list1.append(i)
    text_calendar.append(list1[:7])
    text_calendar.append(list1[7:14])
    text_calendar.append(list1[14:21])
    text_calendar.append(list1[21:28])
    text_calendar.append(list1[28:35])
    text_calendar.append(list1[35:42])

    # все дни месяца
    all_days = list(filter(lambda num: num != 0, list1))

    # Monthly check
    count_all_days = calendar.monthrange(datetime.datetime.today().year, datetime.datetime.today().month)[1]
    if len(all_days) != count_all_days:
        month_update(request, service_id)

    work_days = []
    for work_day in day:
        if work_day.day < datetime.datetime.today().day:
            continue
        work_days.append(work_day.day)

    context = {
        'all_days': text_calendar,
        'service': service,
        'work_days': work_days
    }

    return render(request, 'day_selection.html', context=context)


def month_update(request, service_id):
    service = Service.objects.get(pk=service_id)
    Date.objects.filter(service_id=service_id)

    index_work_days = []
    for i in service.working_days.all():
        index_work_days.append(i.id)

    create_working_days(request, service_id, index_work_days)
    return messages.success(request, "Schedule updated!")


def time_selection(request, service_id, day_id):
    service = Service.objects.get(pk=service_id)
    day = Date.objects.get(day=day_id, service_id=service_id)
    time = Time.objects.select_related('customer').filter(day_id=day.id, customer_id__isnull=True).order_by('id')
    recording_time = RecordingTime.objects.get(service=service_id)

    if not time.exists():
        if str(recording_time) == '00:30':
            freq = '0.5H'
        elif str(recording_time) == '01:00':
            freq = '1H'
        time_list = pd.timedelta_range(start=str(service.opening_time), end=str(service.closing_time),
                                       freq=freq).tolist()
        for i in time_list:
            Time.objects.create(time=str(i)[7:12], day_id=day.id, service_id=service_id)

    context = {
        'service': service,
        'times': time,
        'day': day,
        # 'recording_times': recording_time
    }

    return render(request, 'time_selection.html', context=context)


def add_customer(request, service_id, day_id, time_id):
    service = Service.objects.get(pk=service_id)
    day = Date.objects.get(pk=day_id)

    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            date = form.save(commit=False)
            date.save()
            my_time = Time.objects.filter(pk=time_id)
            my_time.update(customer_id=date.id)
            messages.success(request, "We inform you that the booking was successful!")

            # _____email_____
            from_email = request.POST['email']
            name = request.POST['name']
            surname = request.POST['surname']
            for i in my_time:
                my_time = i
            date_record = datetime.date(datetime.datetime.today().year, datetime.datetime.today().month,
                                        day.day).strftime('%A, %d %B')
            subject = f"Signing up for an Car Workshop {service.name}"
            message = f'Dear {surname} {name}. \n' \
                      f'We inform you that the booking was successful. \n' \
                      f'You are signed up for a service at the {service.name} on {date_record} at {my_time}. \n' \
                      f'Adress: {service.address}. \n\n' \
                      f'Phone number: {service.phone_number}. \n' \
                      f'Email: {service.email}. \n'
            try:
                send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [f'{from_email}'])
            except BadHeaderError:
                return HttpResponse('Ошибка в теме письма.')
            messages.success(request, "A confirmation email has been sent to you with all the information.")
            # ___________
            return redirect('/')
        else:
            messages.error(request, "Даннные введены неверно!")
        return redirect('/')
    else:
        form = CustomerForm()

    context = {
        'form': form,
    }

    return render(request, 'add_customer.html', context=context)


# views for profile
def profile(request, user_id):
    service = Service.objects.get(owner_id=user_id)
    days = Date.objects.filter(service_id=service.id, day__in=[i for i in range(datetime.datetime.today().day, 32)])
    times = Time.objects.filter(service_id=service.id,
                                day_id__in=[i.id for i in days]).order_by('day_id')

    if not request.user.is_authenticated:
        messages.error(request, "You do not have permission to view your profile!")
        return redirect('/')

    context = {
        'service': service,
        'days': days,
        'times': times
    }

    return render(request, 'view_profile.html', context=context)


def day_add(request, service_id, day_id):
    service = Service.objects.get(pk=service_id)

    Date.objects.create(day=day_id, service_id=service_id)
    messages.success(request, "Day successfully added as working day!")

    return redirect(service.get_absolute_url())


def day_update(request, service_id, day_id):
    service = Service.objects.get(pk=service_id)
    recording_time = RecordingTime.objects.all()

    if not request.user.is_authenticated and request.user.id != service.owner:
        messages.error(request, "You do not have permission to perform these actions!")
        return redirect('/')

    if day_id < datetime.datetime.today().day:
        messages.error(request, "This day cannot be active!")
        return redirect(service.get_absolute_url())

    if request.method == 'POST':
        form = CreateDay(request.POST)
        if form.is_valid():
            day = Date.objects.create(day=day_id, service_id=service_id)
            recording_time = request.POST['recording_time']
            opening_time = request.POST['opening_time'] + ':00'
            closing_time = request.POST['closing_time'] + ':00'
            if recording_time == '00:30':
                freq = '0.5H'
            elif recording_time == '01:00':
                freq = '1H'
            time_list = pd.timedelta_range(start=opening_time, end=closing_time, freq=freq).tolist()
            for i in time_list:
                Time.objects.create(time=str(i)[7:12], day_id=day.id, service_id=service_id)
            messages.success(request, "Day successfully added as working day!")
            return redirect(service.get_absolute_url())
        else:
            messages.error(request, "Шncorrect data entered!")
            return redirect(service.get_absolute_url())
    else:
        form = CreateDay()

    context = {
        'form': form,
        'service': service,
        'day': day_id,
        'times': [],
        'recording_times': recording_time}

    return render(request, 'time_selection.html', context=context)


def day_delete(request, service_id, day_id):
    service = Service.objects.get(pk=service_id)

    if not request.user.is_authenticated and request.user.id != service.owner:
        messages.error(request, "You do not have permission to perform these actions!")
        return redirect('/')

    try:
        Date.objects.get(pk=day_id).delete()
        messages.success(request, "Day successfully marked as inactive!")
    except ObjectDoesNotExist:
        messages.error(request, "An error has occurred. Try again or contact administrator!")

    return redirect(service.get_absolute_url())
