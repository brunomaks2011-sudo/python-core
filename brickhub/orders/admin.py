from django.contrib import admin

from .models import Order, OrderItem, OrderStatusEvent, Payment


class ItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    raw_id_fields = ("product",)


class EventInline(admin.TabularInline):
    model = OrderStatusEvent
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("number", "full_name", "phone", "status", "payment_status", "total", "created_at")
    list_filter = ("status", "payment_method", "delivery_method")
    search_fields = ("number", "phone", "email", "last_name")
    inlines = [ItemInline, EventInline]


admin.site.register(Payment)
