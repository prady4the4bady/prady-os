import { App } from 'ags';
import { MenuBar } from './components/MenuBar.js';
import { Dock } from './components/Dock.js';
import { Spotlight } from './components/Spotlight.js';
import { KryosAssistant } from './components/KryosAssistant.js';

App.config({
    style: './style/global.css',
    windows: [
        MenuBar(),
        Dock(),
        Spotlight(),
        KryosAssistant()
    ],
});
