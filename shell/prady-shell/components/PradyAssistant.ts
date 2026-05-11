import { Widget, Variable, App } from 'ags';

const taskStream = Variable('Awaiting tasks...');

export const KryosAssistant = () => Widget.Window({
    name: 'kryos-assistant',
    anchor: ['top', 'bottom', 'right'],
    visible: false,
    child: Widget.Box({
        className: 'assistant-panel',
        vertical: true,
        css: 'min-width: 400px; padding: 20px;',
        children: [
            Widget.Label({
                className: 'assistant-title',
                label: 'Kryos AI Assistant',
                xalign: 0
            }),
            Widget.Scrollable({
                vexpand: true,
                child: Widget.Label({
                    className: 'assistant-stream',
                    label: taskStream.bind(),
                    wrap: true,
                    xalign: 0,
                    yalign: 0
                })
            }),
            Widget.Button({
                className: 'assistant-stop-btn',
                label: 'Stop Execution',
                onClicked: () => {
                    console.log("Sending ABORT signal to prax-agent");
                    taskStream.value += '\n[ABORTED BY USER]';
                }
            })
        ]
    })
});
