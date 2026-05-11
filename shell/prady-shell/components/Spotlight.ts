import { Widget, App } from 'ags';

export const Spotlight = () => Widget.Window({
    name: 'spotlight',
    anchor: ['top', 'bottom', 'left', 'right'],
    visible: false, // Hidden by default, toggled via keybind
    exclusivity: 'ignore',
    keymode: 'exclusive',
    child: Widget.Box({
        className: 'spotlight-overlay',
        vertical: true,
        vexpand: true,
        hexpand: true,
        css: 'background-color: rgba(0,0,0,0.5);',
        children: [
            Widget.Box({
                className: 'spotlight-container',
                vertical: true,
                children: [
                    Widget.Entry({
                        className: 'spotlight-input',
                        placeholderText: 'App search or ask Kryos...',
                        onAccept: (self) => {
                            console.log(`Executing task: ${self.text}`);
                            // Trigger prax-agent via socket or command
                            App.closeWindow('spotlight');
                        }
                    }),
                    Widget.Label({
                        className: 'spotlight-hint',
                        label: 'Press Tab to switch between App Mode and AI Mode'
                    })
                ]
            })
        ]
    })
});
