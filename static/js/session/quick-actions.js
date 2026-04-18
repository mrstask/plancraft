export const QUICK_ACTIONS = {
    ba: [
        { icon: '❓', label: 'Ask me clarifying questions', prompt: 'Please ask me targeted clarifying questions to better understand the problem, users, and their pain points.' },
        { icon: '👤', label: 'Define user personas', prompt: 'Help me define the key user personas for this project — who they are, their goals, and frustrations.' },
        { icon: '🎯', label: 'Identify success metrics', prompt: 'What does success look like for this project? Help me define measurable outcomes.' },
        { icon: '⚠️', label: 'Identify risks & assumptions', prompt: 'What are the key assumptions we are making? What could invalidate this project?' },
        { icon: '📋', label: 'Summarise what we have', prompt: 'Summarise the problem statement and all user stories we have captured so far.' },
    ],
    pm: [
        { icon: '❓', label: 'Ask clarifying questions', prompt: 'Ask me questions to help prioritise stories and define what belongs in the MVP vs later versions.' },
        { icon: '🗂️', label: 'Group stories into epics', prompt: 'Review the current stories and group them into logical epics.' },
        { icon: '🎯', label: 'Define MVP scope', prompt: 'Based on the stories, propose which ones are must-haves for the MVP and why.' },
        { icon: '🔢', label: 'Prioritise all stories', prompt: 'Go through each story and set its priority (must / should / could / won\'t) with a brief rationale.' },
        { icon: '🔍', label: 'Find missing stories', prompt: 'Are there any user stories or edge cases we might have missed given the problem statement?' },
    ],
    architect: [
        { icon: '❓', label: 'Ask clarifying questions', prompt: 'Ask me targeted questions to clarify technical requirements, constraints, and preferences before designing components.' },
        { icon: '🏗️', label: 'Design core components', prompt: 'Based on the stories and epics, propose the core architectural components with their responsibilities and relationships.' },
        { icon: '📁', label: 'Suggest file structure', prompt: 'Propose a concrete file and module structure for this project.' },
        { icon: '🔄', label: 'Define data flow', prompt: 'Describe how data flows between the components — inputs, outputs, and integration points.' },
        { icon: '⚖️', label: 'Key architecture decisions', prompt: 'What are the most important architecture decisions we need to make? Walk me through the trade-offs.' },
        { icon: '⚠️', label: 'Identify technical risks', prompt: 'What are the main technical risks or failure points in this design?' },
    ],
    tdd: [
        { icon: '❓', label: 'Ask clarifying questions', prompt: 'Ask me questions to clarify expected behaviour, edge cases, and acceptance criteria before writing test specs.' },
        { icon: '✅', label: 'Write test specs', prompt: 'Write test specifications in Given/When/Then format for each component.' },
        { icon: '🔲', label: 'Identify edge cases', prompt: 'What edge cases and error scenarios should we cover in the tests?' },
        { icon: '📦', label: 'Propose implementation tasks', prompt: 'Break the work into atomic, independently implementable tasks for the development team.' },
        { icon: '🔗', label: 'Map task dependencies', prompt: 'Review the proposed tasks and identify which ones must be completed before others can start.' },
    ],
    review: [
        { icon: '🔎', label: 'Full review', prompt: '__FULL_REVIEW__' },
        { icon: '📖', label: 'Review stories', prompt: 'Review all user stories for duplicates and quality. Delete duplicates, improve wording where needed.' },
        { icon: '🏗️', label: 'Review components', prompt: 'Review all architectural components for duplicates and unclear responsibilities. Clean them up.' },
        { icon: '📋', label: 'Review decisions', prompt: 'Review all architecture decisions for near-duplicates. Merge or delete redundant ones, improve clarity.' },
        { icon: '✅', label: 'Review test specs', prompt: 'Review all test specifications. Remove duplicates, fill in any empty Given/When/Then fields.' },
        { icon: '📦', label: 'Review tasks', prompt: 'Review all implementation tasks for duplicates and completeness. Clean up descriptions.' },
    ],
};
