begin transaction;

alter table usage_messages add message_count integer default 1;

commit;