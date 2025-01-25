# Static Site Generator - C Preprocessor Syntax

I made this as a quick solution to my unique problem. Although my problem could be solved easily using existing frameworks, but I wanted extremely fast solution requring no setup. So i made a C-macros syntax static site generator.

I usaully make games on [game idea](https://gameidea.org), you can find my work there. Thank you for coming here!

# Usage Examples

In a.html:
```html
#define header(title, subtitle) (
    <header>
        <h1>{title}</h1>
        <h2>{subtitle}</h2>
    </header>
)
```

In b.html:
```html
#include <./a.html>
#define card(image, title, text) (
    <div class="card">
        <img src="{image}" alt="{title}">
        <h3>{title}</h3>
        <p>{text}</p>
    </div>
)
```

# Other Examples

We declare a component using `#define` like this:
![image](https://github.com/user-attachments/assets/82e1243c-443a-4c59-932f-c503ecef6896)

In the above code, the parameters values will be replaced with passed value.


Then we use it like this:

![image](https://github.com/user-attachments/assets/c031daae-0d16-4ffc-a2f6-dae038618d6b)


There is more we can do. Basically, most of C proprocessor is implemented, but there can be some issues in conditinoal thing such as `#ifndef`.
