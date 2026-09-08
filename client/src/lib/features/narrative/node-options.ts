export const entityTypeOptions = [
	{ value: 'character', label: 'Character' },
	{ value: 'location', label: 'Location' },
	{ value: 'organization', label: 'Organization' },
	{ value: 'group', label: 'Group' },
	{ value: 'object', label: 'Object' },
	{ value: 'creature', label: 'Creature' },
	{ value: 'concept', label: 'Concept' },
	{ value: 'other', label: 'Other' }
] as const;

export const eventTypeOptions = [
	{ value: 'story_event', label: 'Story event' },
	{ value: 'discovery', label: 'Discovery' },
	{ value: 'conflict', label: 'Conflict' },
	{ value: 'decision', label: 'Decision' },
	{ value: 'transition', label: 'Transition' },
	{ value: 'revelation', label: 'Revelation' },
	{ value: 'other', label: 'Other' }
] as const;

export const contextTypeOptions = [
	{ value: 'setting', label: 'Setting' },
	{ value: 'time_period', label: 'Time period' },
	{ value: 'social_context', label: 'Social context' },
	{ value: 'rule', label: 'Story rule' },
	{ value: 'mood', label: 'Mood or atmosphere' },
	{ value: 'other', label: 'Other' }
] as const;
