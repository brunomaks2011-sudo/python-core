from django.contrib import admin

from .models import (
    Category, Color, Element, Favorite, Inventory, LegoSet, Minifigure, Part, PartCategory, Product,
    ProductImage, Review, StockNotification, Theme,
)


@admin.register(Color)
class ColorAdmin(admin.ModelAdmin):
    list_display = ("name", "name_uk", "rgb", "bricklink_id", "rebrickable_id", "is_transparent", "is_active")
    search_fields = ("name", "name_uk")
    list_filter = ("is_transparent", "finish", "is_active")


@admin.register(Theme)
class ThemeAdmin(admin.ModelAdmin):
    list_display = ("name", "title", "parent", "is_primary", "show_in_minifigs", "sort_order")
    search_fields = ("name", "title")
    list_filter = ("is_primary", "show_in_minifigs")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "kind", "sort_order", "is_active")
    prepopulated_fields = {"slug": ("name",)}


admin.site.register(PartCategory)


@admin.register(Part)
class PartAdmin(admin.ModelAdmin):
    list_display = ("design_id", "name", "name_uk", "category")
    search_fields = ("design_id", "name", "name_uk")
    list_filter = ("category",)


@admin.register(Element)
class ElementAdmin(admin.ModelAdmin):
    list_display = ("element_id", "part", "color")
    search_fields = ("element_id", "part__design_id")
    raw_id_fields = ("part",)


@admin.register(LegoSet)
class LegoSetAdmin(admin.ModelAdmin):
    list_display = ("number", "name", "theme", "year", "pieces")
    search_fields = ("number", "name")
    list_filter = ("year",)


@admin.register(Minifigure)
class MinifigureAdmin(admin.ModelAdmin):
    list_display = ("fig_number", "bricklink_id", "name", "theme", "year")
    search_fields = ("fig_number", "bricklink_id", "name")


class ImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0


class InventoryInline(admin.StackedInline):
    model = Inventory
    can_delete = False


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("sku", "title", "kind", "condition", "price", "is_active")
    search_fields = ("sku", "title", "search_text")
    list_filter = ("kind", "condition", "is_active", "is_new", "is_rare")
    raw_id_fields = ("lego_set", "part", "minifigure")
    inlines = [InventoryInline, ImageInline]


admin.site.register(Review)
admin.site.register(Favorite)
admin.site.register(StockNotification)
