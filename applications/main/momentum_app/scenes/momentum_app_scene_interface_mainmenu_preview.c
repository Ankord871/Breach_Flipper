// Breach: live preview of the main menu layout.
// Shows where every app will sit for the currently selected Menu Style.
// Up/Left = previous app, Down/Right = next app, Back = return.
// The highlighted slot is the same app that is selected as "Item" in the Mainmenu settings.
#include "../momentum_app.h"
#include <gui/elements.h>

extern const char* const menu_style_names[MenuStyleCount];

typedef struct {
    MomentumApp* app;
} MomentumAppPreviewModel;

#define PREVIEW_TOP 8 // first 8 px are used by the caption

static const char* preview_label(MomentumApp* app, size_t i) {
    return *CharList_get(app->mainmenu_app_labels, i);
}

// One line cell: "N name"
static void preview_row_cell(
    Canvas* canvas,
    MomentumApp* app,
    size_t i,
    int32_t x,
    int32_t y,
    size_t w,
    size_t h,
    Font font,
    bool selected) {
    FuriString* str = furi_string_alloc_printf("%u %s", (unsigned)(i + 1), preview_label(app, i));
    canvas_set_font(canvas, font);
    elements_string_fit_width(canvas, str, w - 3);
    if(selected) {
        canvas_draw_box(canvas, x, y, w, h);
        canvas_set_color(canvas, ColorWhite);
    } else {
        canvas_draw_frame(canvas, x, y, w, h);
    }
    canvas_draw_str(canvas, x + 2, y + (h + 5) / 2, furi_string_get_cstr(str));
    canvas_set_color(canvas, ColorBlack);
    furi_string_free(str);
}

// Box cell: big number on top, name below
static void preview_box_cell(
    Canvas* canvas,
    MomentumApp* app,
    size_t i,
    int32_t x,
    int32_t y,
    size_t w,
    size_t h,
    bool selected) {
    FuriString* str = furi_string_alloc_set(preview_label(app, i));
    canvas_set_font(canvas, FontSecondary);
    elements_string_fit_width(canvas, str, w - 2);
    if(selected) {
        canvas_draw_box(canvas, x, y, w, h);
        canvas_set_color(canvas, ColorWhite);
    } else {
        canvas_draw_frame(canvas, x, y, w, h);
    }
    char num[8];
    snprintf(num, sizeof(num), "%u", (unsigned)(i + 1));
    canvas_set_font(canvas, FontPrimary);
    canvas_draw_str_aligned(canvas, x + w / 2, y + 3, AlignCenter, AlignTop, num);
    canvas_set_font(canvas, FontSecondary);
    canvas_draw_str_aligned(
        canvas, x + w / 2, y + h - 2, AlignCenter, AlignBottom, furi_string_get_cstr(str));
    canvas_set_color(canvas, ColorBlack);
    furi_string_free(str);
}

// Small numbered square for carousel styles
static void preview_square(
    Canvas* canvas,
    size_t i,
    int32_t x,
    int32_t y,
    size_t size,
    bool selected) {
    char num[8];
    snprintf(num, sizeof(num), "%u", (unsigned)(i + 1));
    if(selected) {
        canvas_draw_box(canvas, x, y, size, size);
        canvas_set_color(canvas, ColorWhite);
    } else {
        canvas_draw_frame(canvas, x, y, size, size);
    }
    canvas_set_font(canvas, FontPrimary);
    canvas_draw_str_aligned(canvas, x + size / 2, y + size / 2 + 1, AlignCenter, AlignCenter, num);
    canvas_set_color(canvas, ColorBlack);
}

// Grid that is filled column by column (like Wii, C64, Compact, Vertical)
static void preview_grid(
    Canvas* canvas,
    MomentumApp* app,
    size_t index,
    size_t count,
    size_t cols,
    size_t rows,
    int32_t x0,
    size_t cell_w,
    size_t cell_h,
    Font font,
    bool boxes) {
    size_t page_size = cols * rows;
    size_t page_start = (index / page_size) * page_size;
    for(size_t s = 0; s < page_size; s++) {
        size_t i = page_start + s;
        if(i >= count) break;
        size_t col = s / rows;
        size_t row = s % rows;
        int32_t x = x0 + col * cell_w + (boxes ? col * 3 : 0);
        int32_t y = PREVIEW_TOP + row * cell_h + (boxes ? row : 0);
        if(boxes) {
            preview_box_cell(canvas, app, i, x, y, cell_w, cell_h, i == index);
        } else {
            preview_row_cell(canvas, app, i, x, y, cell_w, cell_h, font, i == index);
        }
    }
}

static void preview_draw_callback(Canvas* canvas, void* _model) {
    MomentumAppPreviewModel* model = _model;
    MomentumApp* app = model->app;
    size_t count = CharList_size(app->mainmenu_app_labels);
    MenuStyle style = momentum_settings.menu_style;

    canvas_clear(canvas);
    canvas_set_color(canvas, ColorBlack);

    // Caption
    char caption[40];
    if(count) {
        snprintf(
            caption,
            sizeof(caption),
            "%s  %u/%u",
            menu_style_names[style],
            (unsigned)(app->mainmenu_app_index + 1),
            (unsigned)count);
    } else {
        snprintf(caption, sizeof(caption), "%s", menu_style_names[style]);
    }
    canvas_set_font(canvas, FontBatteryPercent);
    canvas_draw_str(canvas, 1, 6, caption);
    canvas_draw_str_aligned(canvas, 127, 0, AlignRight, AlignTop, "< >");

    if(!count) {
        canvas_set_font(canvas, FontSecondary);
        canvas_draw_str_aligned(canvas, 64, 36, AlignCenter, AlignCenter, "No menu items");
        return;
    }

    size_t index = CLAMP(app->mainmenu_app_index, count - 1, 0U);

    switch(style) {
    case MenuStyleWii:
        // 3 columns x 2 rows, filled top to bottom, then next column
        preview_grid(canvas, app, index, count, 3, 2, 1, 40, 26, FontSecondary, true);
        break;
    case MenuStyleC64:
        // 2 columns x 5 rows
        preview_grid(canvas, app, index, count, 2, 5, 0, 64, 11, FontSecondary, false);
        break;
    case MenuStyleCompact:
        // 2 columns x 8 rows
        preview_grid(canvas, app, index, count, 2, 8, 0, 64, 7, FontBatteryPercent, false);
        break;
    case MenuStyleVertical:
        // Flipper is held upright: one column, 8 rows
        preview_grid(canvas, app, index, count, 1, 8, 32, 64, 7, FontBatteryPercent, false);
        break;
    case MenuStyleDsi:
    case MenuStyleCoverFlow:
    case MenuStylePs4: {
        // Horizontal row, selected app is highlighted
        int8_t first = (style == MenuStylePs4) ? -1 : -2;
        int8_t last = (style == MenuStylePs4) ? 4 : 2;
        int32_t n = last - first + 1;
        int32_t x0 = 64 - (n * 21) / 2;
        int32_t k = 0;
        for(int8_t o = first; o <= last; o++, k++) {
            int32_t pos = (int32_t)index + o;
            if(style == MenuStylePs4) {
                if(pos < 0 || pos >= (int32_t)count) continue;
            } else {
                pos = ((pos % (int32_t)count) + (int32_t)count) % (int32_t)count;
            }
            preview_square(canvas, pos, x0 + k * 21, 20, 20, o == 0);
        }
        canvas_set_font(canvas, FontPrimary);
        canvas_draw_str_aligned(
            canvas, 64, 58, AlignCenter, AlignBottom, preview_label(app, index));
        break;
    }
    case MenuStyleList:
    case MenuStyleMNTM:
    default: {
        // Vertical list, 3 visible, selected in the middle
        for(int8_t o = -1; o <= 1; o++) {
            size_t pos = (index + count + o) % count;
            preview_row_cell(
                canvas, app, pos, 2, 12 + (o + 1) * 17, 124, 15, FontSecondary, o == 0);
        }
        break;
    }
    }
}

static bool preview_input_callback(InputEvent* event, void* context) {
    MomentumApp* app = context;
    if(event->type != InputTypeShort && event->type != InputTypeRepeat) return false;

    size_t count = CharList_size(app->mainmenu_app_labels);
    if(!count) return false;
    size_t index = CLAMP(app->mainmenu_app_index, count - 1, 0U);

    switch(event->key) {
    case InputKeyLeft:
    case InputKeyUp:
        index = (index + count - 1) % count;
        break;
    case InputKeyRight:
    case InputKeyDown:
        index = (index + 1) % count;
        break;
    default:
        return false;
    }
    app->mainmenu_app_index = index;

    with_view_model(
        app->preview_view, MomentumAppPreviewModel * model, { UNUSED(model); }, true);
    return true;
}

View* momentum_app_preview_view_alloc(MomentumApp* app) {
    View* view = view_alloc();
    view_allocate_model(view, ViewModelTypeLocking, sizeof(MomentumAppPreviewModel));
    view_set_context(view, app);
    view_set_draw_callback(view, preview_draw_callback);
    view_set_input_callback(view, preview_input_callback);
    with_view_model(
        view, MomentumAppPreviewModel * model, { model->app = app; }, false);
    return view;
}

void momentum_app_preview_view_free(View* view) {
    view_free_model(view);
    view_free(view);
}

void momentum_app_scene_interface_mainmenu_preview_on_enter(void* context) {
    MomentumApp* app = context;
    view_dispatcher_switch_to_view(app->view_dispatcher, MomentumAppViewPreview);
}

bool momentum_app_scene_interface_mainmenu_preview_on_event(
    void* context,
    SceneManagerEvent event) {
    UNUSED(context);
    UNUSED(event);
    return false; // Back is handled by the scene manager
}

void momentum_app_scene_interface_mainmenu_preview_on_exit(void* context) {
    UNUSED(context);
}
